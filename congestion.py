# calculated congestion index for a topology
import os
import argparse
import time
import tracegraph as tg
import logging
import json
from networkx.readwrite import json_graph
from collections import defaultdict
from itertools import chain
import timetools as tt

BIN = 600  # bin size in sec
CH_MTD = "cpt_poisson&MBIC"  # changepoint method for binning
LINK_THRESHOLD = 0.5  # threshold for link inference
NODE_THRESHOLD = 0.5  # threshold for node inference


def main():
    t1 = time.time()
    # log to data_collection.log file
    logging.basicConfig(filename='congestion.log', level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S %z')

    parser = argparse.ArgumentParser()
    parser.add_argument("-g", "--topology",
                        help="topology .json file",
                        action="store")
    parser.add_argument("-s", "--suffix",
                        help="the suffix of files to be considered in the directory",
                        action="store")
    parser.add_argument("-d", "--directory",
                        help="the directory containing the result of change detection",
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

    if not all(map(bool, args_dict.values())):
        # all the parameters must be set
        print args.help
        return

    try:
        with open(args.topology, 'r') as fp:
            topo = json.load(fp)
    except IOError as e:
        logging.error(e)
        return

    # load topo from json file
    topo = json_graph.node_link_graph(topo)
    logging.info("%d node, %d links" % (len(topo.nodes()), len(topo.edges())))

    if not os.path.exists(args.directory):
        logging.error("%s doesn't exist." % args.directory)
        return

    # files of detected RTT changes
    files = []
    for f in os.listdir(args.directory):
        if f.endswith(args.suffix) and not f.startswith('~'):
            files.append(os.path.join(args.directory, f))

    if not files:
        logging.error("No file with suffix %s in %s" % (args.suffix, args.directory))
        return

    try:
        begin = tt.string_to_epoch(args.beginTime)
    except (ValueError, TypeError):
        logging.critical("Wrong --beginTime format. Should be %s." % '%Y-%m-%d %H:%M:%S %z')
        return

    try:
        stop = tt.string_to_epoch(args.stopTime)
    except (ValueError, TypeError):
        logging.critical("Wrong --stopTime format. Should be %s." % '%Y-%m-%d %H:%M:%S %z')
        return

    # log parameter to graph
    topo.graph['congestion_begin'] = begin
    topo.graph['congestion_end'] = stop
    topo.graph['cpt_method'] = CH_MTD
    topo.graph['cpt_bin_size'] = BIN

    pb2links = defaultdict(list)
    pb2nodes = defaultdict(list)
    t3 = time.time()
    # learn probe to link map, s.t. given a probe change trace, we know which links are meant to be updated
    # initialize the congestion and inference field for each link and node
    for l in topo.edges_iter():
        topo[l[0]][l[1]]['score'] = defaultdict(int)
        topo[l[0]][l[1]]['inference'] = dict()
        for pb in topo[l[0]][l[1]]['probe']:
            pb2links[pb].append(l)

    # initialize the congestion and inference field for each link and node
    # for each node, a probe set with divergent paths are as well needed to see if the congestion is caused by the node
    # learn this probe set for each node and form a probe to node dict
    for n in topo.nodes_iter():
        topo.node[n]['score'] = defaultdict(int)
        topo.node[n]['inference'] = dict()

        p2n = defaultdict(lambda: {n})  # all the nodes traversed by probes on surrounding links
        for neighbour in topo.neighbors(n):
            for pb in topo[n][neighbour]["probe"]:
                p2n[pb].add(neighbour)
        n_pb, res = tg.divergent_set(p2n, {n})  # n is the only common node allowed
        # logging.debug("Node %r: %d possible divergent pbs sets of size %d" % (n, len(res), n_pb))
        if res:
            topo.node[n]['probe'] = res[0]['member']
            res[0]['attr'].remove(n)
            topo.node[n]['effective_neighbour'] = list(res[0]['attr'])
            for pb in topo.node[n]['probe']:
                pb2nodes[pb].append(n)
    t4 = time.time()
    logging.info("Topo data preparation in %.2f sec" % (t4-t3))

    # calculate the change sum per bin per link, per node
    # incrementally update the entire, file by file
    for f in files:
        tg.change_binsum(f, CH_MTD, topo, pb2links, pb2nodes, BIN, begin, stop)

    # normalize the change count per bin per link by the probe numbers per link
    t3 = time.time()
    for l in topo.edges_iter():
        pb_count = len(topo[l[0]][l[1]]['probe'])
        try:
            for t in topo[l[0]][l[1]]['score']:
                topo[l[0]][l[1]]['score'][t] /= float(pb_count)
        except ZeroDivisionError:
            logging.error("%r has no probe." % topo[l[0]][l[1]])

    for n in topo.nodes_iter():
        pb_count = len(topo.node[n]['probe'])
        if pb_count:
            for t in topo.node[n]['score']:
                topo.node[n]['score'][t] /= float(pb_count)
    t4 = time.time()
    logging.info("Normalize change index in %.2f sec" % (t4-t3))

    # perform change location inference
    tg.change_inference_node(topo, NODE_THRESHOLD, BIN, begin, stop)
    tg.change_inference_link(topo, LINK_THRESHOLD, BIN, begin, stop)

    # formatting congestion and inference filed for js plot
    t3 = time.time()
    for l in topo.edges_iter():
        topo[l[0]][l[1]]['score'] = [{"epoch": i[0], "value": round(i[1], 3)}
                                     for i in sorted(topo[l[0]][l[1]]['score'].items(), key=lambda s: s[0])]
        topo[l[0]][l[1]]['inference'] = [{"epoch": i[0], "value": i[1]}
                                         for i in sorted(topo[l[0]][l[1]]['inference'].items(), key=lambda s: s[0])
                                         if i[1] != tg.NEG]
    for n in topo.nodes_iter():
        topo.node[n]['inference'] = [{"epoch": i[0], "value": i[1]}
                                     for i in sorted(topo.node[n]['inference'].items(), key=lambda s: s[0])
                                     if i[1] != tg.NEG]
    t4 = time.time()
    logging.info("Change index and inference formatting in %.2f sec" % (t4 - t3))

    # serialize graph to json
    t3 = time.time()
    res = dict()
    res['congestion'] = True
    res['directed'] = topo.is_directed()
    res['multigraph'] = topo.is_multigraph()
    res['graph'] = topo.graph
    res['nodes'] = [dict(chain(v.items(), [('id', k)])) for k, v in topo.nodes_iter(data=True)]
    res['links'] = [dict(chain(v.items(), [('source', src), ('target', dst)])) for src, dst, v in topo.edges_iter(data=True)]
    t4 = time.time()
    logging.info("nx.Grape to dict in %.2f sec" % (t4-t3))

    json.dump(res, open(args.outfile, 'w'))

    t2 = time.time()
    logging.info("Whole task finished in %.2f sec" % (t2 - t1))


if __name__ == '__main__':
    main()
