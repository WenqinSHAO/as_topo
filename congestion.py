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
CON_THRESHOLD = 0.5  # threshold of change index


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
    logging.debug("%d node, %d links" % (len(topo.nodes()), len(topo.edges())))

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

    # learn probe to link map
    # initialize the congestion and inference field for each link and node
    pb2links = defaultdict(list)

    for l in topo.edges_iter():
        topo[l[0]][l[1]]['congestion'] = defaultdict(int)
        topo[l[0]][l[1]]['inference'] = defaultdict(bool)
        for pb in topo[l[0]][l[1]]['probe']:
            pb2links[pb].append(l)

    for n in topo.nodes_iter():
        topo.node[n]['inference'] = defaultdict(bool)

    # calculate the change sum per bin per link
    # incrementally handle each file
    for f in files:
        t3 = time.time()
        data = None
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
        except IOError as e:
            logging.critical(e)

        if data:
            for pb in data:
                pb_rec = data[pb]
                if pb_rec:
                    for t, v in zip(pb_rec.get("epoch", []), pb_rec.get(CH_MTD, [])):
                        if begin <= t <= stop:
                            t = (t // BIN) * BIN
                            for l in pb2links.get(pb, []):
                                topo[l[0]][l[1]]['congestion'][t] += v
        t4 = time.time()
        logging.debug("%s handled in %.2f sec" % (f, t4-t3))

    # normalize the change count per bin per link by the probe numbers per link
    t3 = time.time()
    for l in topo.edges_iter():
        pb_count = len(topo[l[0]][l[1]]['probe'])
        assert pb_count != 0
        for t in topo[l[0]][l[1]]['congestion']:
            topo[l[0]][l[1]]['congestion'][t] /= pb_count
    t4 = time.time()
    logging.debug("Normalize congestion index in %.2f sec" % (t4-t3))

    # congestion inference for each bin
    t3 = time.time()
    for t in range((begin // BIN) * BIN, ((stop // BIN) + 1) * BIN, BIN):
        for l in topo.edges_iter():
            if topo[l[0]][l[1]]['congestion'][t] >= CON_THRESHOLD:
                branches = tg.find_branches(topo, l[0], l[1])
                ext = {k: [i for i in v if i[-1] > 0] for k, v in branches.items()}
                sib = {k: [i for i in v if i[-1] == 0] for k, v in branches.items()}
                ext_con_count = {k: sum([1 if topo[i[0]][k]['congestion'][t] >= CON_THRESHOLD else 0 for i in v]) for k, v in ext.items()}
                sib_con_count = {k: sum([1 if topo[i[0]][k]['congestion'][t] >= CON_THRESHOLD else 0 for i in v]) for k, v in sib.items()}

                if ext_con_count[l[0]] > 1 and ext_con_count[l[1]] > 1:
                    topo[l[0]][l[1]]['inference'][t] = True
                for n, other in [l, l[::-1]]:
                    if ext_con_count[n] > 1 and len(ext[other]) == 0:
                        if sib_con_count[n] > 0:
                            topo.node[n]['inference'][t] = True
                        if sib_con_count[other] > 0:
                            topo.node[other]['inference'][t] = True
                        else:
                            topo[l[0]][l[1]]['inference'][t] = True
    t4 = time.time()
    logging.debug("Congestion inference in %.2f sec" % (t4 - t3))

    # formatting congestion and inference filed for js plot
    t3 = time.time()
    for l in topo.edges_iter():
        topo[l[0]][l[1]]['congestion'] = [{"epoch": i[0], "value": round(i[1], 3)}
                                          for i in sorted(topo[l[0]][l[1]]['congestion'].items(), key=lambda s: s[0])]
        topo[l[0]][l[1]]['inference'] = [{"epoch": i[0], "value": i[1]}
                                         for i in sorted(topo[l[0]][l[1]]['inference'].items(), key=lambda s: s[0])]
    for n in topo.nodes_iter():
        topo.node[n]['inference'] = [{"epoch": i[0], "value": i[1]}
                                     for i in sorted(topo.node[n]['inference'].items(), key=lambda s: s[0])]
    t4 = time.time()
    logging.debug("Congestion index and inference formatting in %.2f sec" % (t4 - t3))

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
    logging.debug("nx.Grape to dict in %.2f sec" % (t4-t3))

    json.dump(res, open(args.outfile, 'w'))

    t2 = time.time()
    logging.info("Whole task finished in %.2f sec" % (t2 - t1))


if __name__ == '__main__':
    main()
