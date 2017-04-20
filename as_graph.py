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


def worker(fn, end=None):
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
        # TODO: parameterize the traceroutes considered for each probe
        # current only first 300 traceroute is considered in construting the graph;
        # the better is to make it a configurable input that reflects in the final graph
        # e.g. given a human readable time range
        # TODO: associate source AS with a new attribute indicating the probes hosted
        # TODO: in javascript, when click on a source probe, visualize all the edges taken by the probe
        if end:
            as_path = [[j for j in i if j not in RM_HOP] for i in traceroute[pb]['asn_path'][:336] if end in i]
        else:
            as_path = [[j for j in i if j not in RM_HOP] for i in traceroute[pb]['asn_path'][:336]]
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
        if n in source:
            g.node[n]['termination'] = 1
            g.node[n]['hosting'] = hosting[n]
        elif n in ixp:
            g.node[n]['termination'] = 2
        elif n in dest:
            g.node[n]['termination'] = 3
        else:
            g.node[n]['termination'] = 4

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
    args = parser.parse_args()

    if not args.directory or not args.suffix:
        print args.help
        return
    else:
        trace_dir = args.directory

    if not os.path.exists(trace_dir):
        logging.critical("%s doesn't existe." % trace_dir)
        return

    files = []
    for f in os.listdir(trace_dir):
        if f.endswith(args.suffix) and not f.startswith('~'):
            files.append(os.path.join(trace_dir, f))

    if not files:
        logging.INFO("No file found in %s, exited." % trace_dir)
        return

    pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())
    res = pool.map(worker_wrapper, itertools.izip(files, itertools.repeat(args.end)))

    g = t.compose_all_modify(res)

    # listfy the probe set, otherwise cannot be serialized
    for e in g.edges_iter():
        g[e[0]][e[1]]['probe'] = list(g[e[0]][e[1]]['probe'])

    for n in g.nodes_iter():
        if 'hosting' in g.node[n]:
            g.node[n]['hosting'] = list(g.node[n]['hosting'])

    d = t.node_link_data_modify(g)
    json.dump(d, open('graph.json', 'w'))

    t2 = time.time()
    logging.info("Graph formulated and saved in %.2f sec." % (t2-t1))


if __name__ == '__main__':
    main()
