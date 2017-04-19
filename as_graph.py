import tracegraph as t
import networkx as nx
import json
import traceback
import logging
import os
import argparse
import multiprocessing

RM_HOP = ['', 'Invalid IP address', 'this', 'private', 'CGN', 'host', 'linklocal',
          'TEST-NET-1', 'TEST-NET-2', 'TEST-NET-3', 'benchmark', '6to4',
          'multicast', 'future', 'broadcast']

def worker(fn):
    try:  # load AS_path file
        with open(os.path.join(fn), 'r') as fp:
            traceroute = json.load(fp)
    except IOError as e:
        logging.error(e)
        return nx.Graph()

    g = nx.Graph()
    source = set()
    dest = set([226])
    ixp = set()

    for pb in traceroute:
        as_path = [[j for j in i if j not in RM_HOP] for i in traceroute[pb]['asn_path'][:300] if 226 in i]
        if as_path:
            for p in as_path:
                last_idx = len(p)
                for idx, h in enumerate(p):
                    if idx == 0:
                        source.add(h)
                    elif idx == last_idx:
                        dest.add(h)
                    elif isinstance(h, (str, unicode)):
                        ixp.add(h)
            t.path_to_graph(as_path, pb, g)

    #logging.debug("IXPs: %r" % ixp)

    for e in g.edges():
        g[e[0]][e[1]]['probe'] = list(g[e[0]][e[1]]['probe'])

    for n in g:
        if n in source:
            g.node[n]['termination'] = 1
        elif n in ixp:
            g.node[n]['termination'] = 2
        elif n in dest:
            g.node[n]['termination'] = 3
        else:
            g.node[n]['termination'] = 4
    return g


def worker_wrapper(args):
    try:
        return worker(args)
    except Exception:
        logging.critical("Exception in worker.")
        traceback.print_exc()
        raise

def main():
    # log to data_collection.log file
    logging.basicConfig(filename='as_graph.log', level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S %z')

    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--directory",
                        help="the directory storing data.",
                        action="store")
    args = parser.parse_args()

    if not args.directory:
        print args.help
        return
    else:
        trace_dir = args.directory

    if not os.path.exists(trace_dir):
        logging.critical("%s doesn't existe." % trace_dir)
        return

    files = []
    for f in os.listdir(trace_dir):
        if f.endswith('5010.json') and not f.startswith('~'):
            files.append(os.path.join(trace_dir, f))

    pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())
    res = pool.map(worker_wrapper, files)

    g = t.compose_all_modify(res)
    d = t.node_link_data_modify(g)
    json.dump(d, open('graph.json', 'w'))


if __name__ == '__main__':
    main()
