import tracegraph as t
import networkx as nx
import json
import traceback
import logging
import os
import argparse
import multiprocessing
import itertools
from ast import literal_eval
import time
from collections import defaultdict
import timetools as tt

# hops to be removed in as path
RM_HOP = ['', 'Invalid IP address', 'this', 'private', 'CGN', 'host', 'linklocal',
          'TEST-NET-1', 'TEST-NET-2', 'TEST-NET-3', 'benchmark', '6to4',
          'multicast', 'future', 'broadcast']


def type_convert(s):
    """ convert string in data/pb.csv to corresponding types

    Args:
        s (string): could be "1124", "US", "None", "True", "12.12.34.56/24", "('da', 'cd', 'ef')"

    Returns:
        "1124" -> 1124; "None" -> None; "US" -> US; "('da', 'cd', 'ef')" -> ('da', 'cd', 'ef')
    """
    try:
        return literal_eval(s)
    except (SyntaxError, ValueError):
        return s


def worker(fn, end=None, begin=None, stop=None):
    """for each given file fn, read the paths sequences for each probe and create a graph out of these paths

    Args:
        fn (str): file to be handled
        end (str or int): a priori known destination of measurement. use it to filter out paths not ended there.

    Return:
        g (nx.Graph)
    """
    t3 = time.time()
    try:  # load AS_path file
        with open(os.path.join(fn), 'r') as fp:
            traceroute = json.load(fp)
    except IOError as e:
        logging.error(e)
        return nx.Graph()

    end = type_convert(end) if end else None

    g = nx.Graph()
    source = set()
    dest = set()
    ixp = set()
    hosting = defaultdict(set)

    if end:
        dest.add(end)

    for pb in traceroute:
        if begin:
            try:
                begin_idx = next(i for i, v in enumerate(traceroute[pb]['epoch']) if v >= begin)
            except StopIteration:
                begin_idx = None
        else:
            begin_idx = None
        if stop:
            try:
                stop_idx = next(i for i, v in enumerate(traceroute[pb]['epoch']) if v > stop)
            except StopIteration:
                stop_idx = None
        else:
            begin_idx = None
        #logging.debug("Probe %s, begin idx = %r, stop idx = %r" % (pb, begin_idx, stop_idx))
        if end:
            if begin or stop:
                as_path = [[j for j in i if j not in RM_HOP] for i in traceroute[pb]['asn_path'][begin_idx:stop_idx] if end in i]
            else:
                try:
                    as_path = [next([j for j in i if j not in RM_HOP] for i in traceroute[pb]['asn_path'] if end in i)]
                except StopIteration:
                    as_path = []
        else:
            if begin or stop:
                as_path = [[j for j in i if j not in RM_HOP] for i in traceroute[pb]['asn_path'][begin_idx:stop_idx]]
            else:
                try:
                    as_path = [next([j for j in i if j not in RM_HOP] for i in traceroute[pb]['asn_path'])]
                except StopIteration:
                    as_path = []
        if as_path:
            for p in as_path:
                last_idx = len(p) - 1
                for idx, h in enumerate(p):
                    if idx == 0:
                        source.add(h)
                        hosting[h].add(pb)
                    elif idx == last_idx:
                        dest.add(h)
                    elif isinstance(h, (str, unicode)):
                        ixp.add(h)
            t.path_to_graph(as_path, pb, g)

    for n in g:
        # 1 for source; 2 for ixp; 3 for dst; 4 for all the others
        # 4 is always added
        attr = defaultdict(set)
        if n in source:
            attr['tag'].add(1)
            attr['hosting'] = hosting[n]
        if n in ixp:
            attr['tag'].add(2)
        if n in dest:
            attr['tag'].add(3)
        if not attr.get('tag'):
            attr['tag'].add(4)
        g.node[n] = attr

    t4 = time.time()
    logging.info("%s handled in %.2f sec." % (fn, t4-t3))
    return g


def worker_wrapper(args):
    try:
        return worker(*args)
    except Exception:
        logging.critical("Exception in worker.")
        traceback.print_exc()
        raise


def main():
    t1 = time.time()
    # log to data_collection.log file
    logging.basicConfig(filename='as_graph.log', level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S %z')

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory",
                        help="the directory storing data.",
                        action="store")
    parser.add_argument("-s", "--suffix",
                        help="the suffix of files to be considered in the directory",
                        action="store")
    parser.add_argument("-e", "--end",
                        help="if all the measurements have a common destination, specify it with this flag",
                        action="store")
    parser.add_argument("-b", "--beginTime",
                        help="the beginning moment for traceroute rendering, format %s" % "%%Y-%%m-%%d %%H:%%M:%%S %%z",
                        action='store')
    parser.add_argument("-t", "--stopTime",
                        help="the ending moment for traceroute rendering, format %s" % "%%Y-%%m-%%d %%H:%%M:%%S %%z",
                        action='store')
    parser.add_argument("-o", "--outfile",
                        help="Specify the name of output .json file",
                        action="store")
    args = parser.parse_args()
    args_dict = vars(args)
    if not args.directory or not args.suffix:
        print args.help
        return
    else:
        trace_dir = args.directory

    if not os.path.exists(trace_dir):
        logging.critical("%s doesn't exist." % trace_dir)
        return

    files = []
    for f in os.listdir(trace_dir):
        if f.endswith(args.suffix) and not f.startswith('~'):
            files.append(os.path.join(trace_dir, f))

    if not files:
        logging.INFO("No file found in %s, exited." % trace_dir)
        return

    if args.beginTime:
        try:
            begin = tt.string_to_epoch(args.beginTime)
        except (ValueError, TypeError):
            logging.critical("Wrong --beginTime format. Should be %s." % '%Y-%m-%d %H:%M:%S %z')
            return
    else:
        begin = None

    if args.beginTime:
        try:
            stop = tt.string_to_epoch(args.stopTime)
        except (ValueError, TypeError):
            logging.critical("Wrong --stopTime format. Should be %s." % '%Y-%m-%d %H:%M:%S %z')
            return
    else:
        stop = None

    if not begin and not stop:
        logging.info("None begin and stop time input, default to consider the first traceroutes of each probe")

    pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())
    res = pool.map(worker_wrapper,
                   itertools.izip(files, itertools.repeat(args.end),
                                  itertools.repeat(begin), itertools.repeat(stop)))

    g = t.graph_union(res)

    # listfy the node/link attributes, otherwise cannot be serialized
    for e in g.edges_iter():
        g[e[0]][e[1]]['probe'] = list(g[e[0]][e[1]]['probe'])

    for n in g.nodes_iter():
        g.node[n]['tag'] = list(g.node[n]['tag'])
        if 'hosting' in g.node[n]:
            g.node[n]['hosting'] = list(g.node[n]['hosting'])

    # graph attributes storing the commend used to create the graph
    for k, v in args_dict.items():
        g.graph[k] = v

    d = t.node_link_data_modify(g)

    out_fn = args.outfile if args.outfile else 'graph.json'
    json.dump(d, open(out_fn, 'w'))

    t2 = time.time()
    logging.info("Graph formulated and saved in %.2f sec." % (t2-t1))


if __name__ == '__main__':
    main()
