import networkx as nx
from itertools import count, chain
from collections import defaultdict
import time
import json
import logging
import timetools as tt

_attrs = dict(id='id', source='source', target='target', key='key', name='name', src_name='src_name', tgt_name='tgt_name')

SURE, LIKELY, NEG = 2, 1, 0

def path_to_graph(paths, probe, g):
    """give a series of paths attached to a given probe, add them to graph g

    Args:
        paths (list of list of hops): it contains a list of path, which is a list of hops from source to dest
        probe: (int or string): the name of the probe from which the above path measurements are performed
        g: (nx.Graph): the graph object to which new nodes and edges are added
    """
    for p in paths:
        for e in zip(p[:-1], p[1:]):
            if e not in g.edges():
                g.add_edge(e[0], e[1], probe=set([]))
            g[e[0]][e[1]]['probe'].add(probe)


def node_link_data_modify(G, attrs=_attrs):
    """dumps a nx.Graph to json compatible with visualization with d3
    It is a modified version of node_link_data() function provided in nx library.
    It fixes a potential issue where the the ids of nodes is different from thoses used in edges, which leads to error
    when visulaizing the graph.

    Args:
        G (nx.Graph or nx.MultiGraph): the graph to be dumpped
        attrs (dict): attributes need when dumpping the graph

    Returns:
        data (dict)
    """
    multigraph = G.is_multigraph()
    id_ = attrs['id']
    name = attrs['name']
    source = attrs['source']
    target = attrs['target']
    src_name = attrs['src_name']
    tgt_name = attrs['tgt_name']
    # Allow 'key' to be omitted from attrs if the graph is not a multigraph.
    key = None if not multigraph else attrs['key']
    if len(set([source, target, key])) < 3:
        raise nx.NetworkXError('Attribute names are not unique.')
    mapping = dict(zip(G, count()))
    data = {}
    data['directed'] = G.is_directed()
    data['multigraph'] = multigraph
    data['graph'] = G.graph
    data['nodes'] = [dict(chain(G.node[n].items(), [(id_, mapping[n]), (name, n)])) for n in G]
    # in the original version the over line goes (id_, n), can causes the id to be different from that of edges
    if multigraph:
        data['links'] = [
            dict(chain(d.items(),
                       [(source, mapping[u]), (target, mapping[v]), (key, k)]))
            for u, v, k, d in G.edges_iter(keys=True, data=True)]
    else:
        data['links'] = [
            dict(chain(d.items(),
                       [(source, mapping[u]), (src_name, u), (target, mapping[v]), (tgt_name, v)]))
            for u, v, d in G.edges_iter(data=True)]

    return data


def compose_modify(G, H):
    """combine two given graphs that might have overlapped edges and nodes.
    It is a modified version of compose() function in nx lib.

    Args:
        G (nx.Graph): multigraph class is current not supported
        H (nx.Graph): multigraph class is current not supported

    Returns:
        R (nx.Graph): the combined graph

    """
    if not G.is_multigraph() == H.is_multigraph() == False:
        raise nx.NetworkXError('Doesn\'t handle multi-graph.')

    R = nx.Graph()

    for n, d in chain(G.nodes_iter(data=True), H.nodes_iter(data=True)):
        # more complex logic merging attributes of node can be added here.
        if n in R.nodes_iter():
            dd = dict()
            d1 = R.node[n]
            dd['tag'] = d1['tag'] | d['tage']
            if 'hosting' in d or 'hosting' in d1:
                dd['hosting'] = set()
                for di in [d, d1]:
                    dd['hosting'].update(di.get('hosting', iter([])))
        else:
            dd = d
        R.add_node(n, dd)

    for src, tgt, d in chain(H.edges_iter(data=True), G.edges_iter(data=True)):
        # if the edge is already present in the graph, for each of its attribute (key), extend the list
        if (src, tgt) in R.edges_iter():
            dd = defaultdict(set)
            d1 = R[src][tgt]
            for di in (d1, d):
                for k, v in di.iteritems():
                    dd[k].update(v)
        else:
            dd = d
        R.add_edge(src, tgt, dd)

    return R


def compose_all_modify(graphs):
    """combine a list of graphs

    Args:
        graphs (list of nx.Graph)

    Returns:
        C (nx.graph): combined graph
    """
    graphs = iter(graphs)
    C = next(graphs)
    for H in graphs:
        C = compose_modify(C, H)
    return C


def change_binsum(fn, method, g, pb2links, pb2nodes, bin_size, begin, stop):
    """calculate binned sum of RTT changes for each link and node in a given topo

    Args:
        fn (string): path to the RTT file
        method (string): field in the file to be extracted as the result of change detection
        g (nx.Graph): network topology learnt from traceroute; link is annotated with probes traverse it
        pb2links (dict): {probe id : [link in g (n1, n2),...]}
        pb2nodes (dict): {probe id: [nodes in g...]}
        bin_size (int): the size of bin in seconds
        begin (int): sec since epoch from which records in fn is considered
        stop (int): sec since epoch till which records in fn is considered

    Notes:
        no return will be provided. update is directly applied to g.
        g has to be initialized for each of its link and node a dictionary "score", default to int type.
    """
    t1 = time.time()

    try:
        with open(fn, 'r') as fp:
            data = json.load(fp)
    except IOError as e:
        logging.critical(e)
        return

    if 'data' in locals() and data:
        for pb in data:
            pb_rec = data[pb]
            if pb_rec:
                for t, v in zip(pb_rec.get("epoch", []), pb_rec.get(method, [])):
                    if begin <= t <= stop:
                        t = (t // bin_size) * bin_size
                        for l in pb2links.get(pb, []):
                            g[l[0]][l[1]]['score'][t] += v
                        for n in pb2nodes.get(pb, []):
                            g.node[n]['score'][t] += v
    t2 = time.time()
    logging.debug("%s handled in %.2f sec" % (fn, t2 - t1))


def change_inference_node(g, node_threshold, bin_size, begin, stop):
    """perform node change location inference

    Args:
        g (nx.Graph): network topology learnt from traceroute; link is annotated with probes traverse it
        node_threshold (float): parameter for node inference; minimum portion of trace traversing that node experience change
        bin_size (int): the size of bin in seconds
        begin (int): sec since epoch from which records in fn is considered
        stop (int): sec since epoch till which records in fn is considered

    Notes:
        no return will be provided. update is directly applied to g.
        g has to be initialized for each of its node a dictionary "inference", default to int type.
        2 (SURE) for inferred (pretty sure) as cause
        1 (LIKELY) for susceptible (not so sure) as cause
    """
    t1 = time.time()
    for t in range((begin // bin_size) * bin_size, ((stop // bin_size) + 1) * bin_size, bin_size):
        for n in g.nodes_iter():
            if len(g.node[n]['probe']) > 1 and g.node[n]['score'][t] > node_threshold:
                g.node[n]['inference'][t] = SURE
    t2 = time.time()
    logging.debug("Node congestion inference in %.2f sec" % (t2 - t1))


def change_inference_link(graph, link_threshold, bin_size, begin, stop):
    """perform link change location inference

    Args:
        graph (nx.Graph): network topology learnt from traceroute; link is annotated with probes traverse it
        link_threshold (float): parameter for link inference; minimum portion of trace on that link experience change
        bin_size (int): the size of bin in seconds
        begin (int): sec since epoch from which records in fn is considered
        stop (int): sec since epoch till which records in fn is considered

    Notes:
        no return will be provided. update is directly applied to g.
        g has to be initialized for each of its link a dictionary "inference", default to int type.
        2 (SURE) for inferred (pretty sure) as cause
        1 (LIKELY) for susceptible (not so sure) as cause
    """

    call_depth = []

    def helper(g, l, t):

        call_depth.append(0)
        if len(call_depth) > 2:
            logging.info("%d level deep Call at %s: %r" % (len(call_depth), tt.epoch_to_string(t), l))

        if t in g[l[0]][l[1]]['inference']:
            call_depth.pop()
            return g[l[0]][l[1]]['inference'][t]

        # a safe for case 3
        if g[l[0]][l[1]]["score"][t] <= link_threshold:
            return NEG

        branches = find_branches(g, l[0], l[1])
        ext = {k: [i for i in v if i[-1] > 0] for k, v in branches.items()}
        ext_con_count_abs = {
            k: sum([1 if g[i[0]][k]['score'][t] > link_threshold else 0 for i in v]) for
            k, v in ext.items()}
        ext_con_count_prop = {
            k: sum([1 if g[i[0]][k]['score'][t] > float(i[2]) / i[1] * link_threshold else 0 for i in v])
            for
            k, v in ext.items()}

        # 1/ l has multiple extension branches at both sides
        if ext_con_count_prop[l[0]] > 1 and ext_con_count_prop[l[1]] > 1:
            g[l[0]][l[1]]['inference'][t] = SURE
            call_depth.pop()
            return SURE
        # 2/ only one extension branch at the one side
        elif len(ext[l[0]]) == 1 and ext_con_count_prop[l[1]] > 1:
            # if the trunk that is ext[l[0]][0] is not responsible for change, then current link must be
            if ext[l[0]][0][1] == ext[l[0]][0][2]:
                g[l[0]][l[1]]['inference'][t] = LIKELY
                call_depth.pop()
                return LIKELY
            else:  # ext[l[0]][0][1] > ext[l[0]][0][2]:
                if ext_con_count_abs[l[0]] < 1:
                    g[l[0]][l[1]]['inference'][t] = SURE
                    call_depth.pop()
                    return SURE
                else:
                    trunk = (l[0], ext[l[0]][0][0])  # the only extension branch on l[0]
                    logging.debug("Dependence chain: %s, %r -> %r" % (tt.epoch_to_string(t), l, trunk))
                    trunk_res = helper(g, trunk, t)
                    if trunk_res == NEG:
                        g[l[0]][l[1]]['inference'][t] = SURE
                        call_depth.pop()
                        return SURE
                    else:
                        g[l[0]][l[1]]['inference'][t] = NEG
                        call_depth.pop()
                        return NEG
        elif len(ext[l[1]]) == 1 and ext_con_count_prop[l[0]] > 1:
            if ext[l[1]][0][1] == ext[l[1]][0][2]:
                g[l[0]][l[1]]['inference'][t] = LIKELY
                call_depth.pop()
                return LIKELY
            else:  # ext[l[1]][0][1] > ext[l[1]][0][2]:
                if ext_con_count_abs[l[1]] < 1:
                    g[l[0]][l[1]]['inference'][t] = SURE
                    call_depth.pop()
                    return SURE
                else:
                    trunk = (l[1], ext[l[1]][0][0])  # the only extension branch on l[0]
                    logging.debug("Dependence chain: %s, %r -> %r" % (tt.epoch_to_string(t), l, trunk))
                    trunk_res = helper(g, trunk, t)
                    if trunk_res == NEG:
                        g[l[0]][l[1]]['inference'][t] = SURE
                        call_depth.pop()
                        return SURE
                    else:
                        g[l[0]][l[1]]['inference'][t] = NEG
                        call_depth.pop()
                        return NEG
        # 3/ both sides have only only one extension branch
        elif len(ext[l[0]]) == 1 and len(ext[l[1]]) == 1:
            if ext[l[0]][0][1] == ext[l[0]][0][2] or ext[l[1]][0][1] == ext[l[1]][0][2]:
                g[l[0]][l[1]]['inference'][t] = LIKELY
                call_depth.pop()
                return LIKELY
            else:  # both extension branches contains more probes than the current one
                if ext_con_count_abs[l[0]] < 1 and ext_con_count_abs[l[1]] < 1:
                    g[l[0]][l[1]]['inference'][t] = SURE
                    call_depth.pop()
                    return SURE
                else:
                    trunk_l0 = (l[0], ext[l[0]][0][0])
                    trunk_l1 = (l[1], ext[l[1]][0][0])
                    logging.debug(
                        "Dependence chain: %s, %r -> (%r, %r) \n%r\n%r\n%r" %
                        (tt.epoch_to_string(t), l, trunk_l0, trunk_l1,
                         g[l[0]][l[1]]['probe'], g[trunk_l0[0]][trunk_l0[1]]['probe'], g[trunk_l1[0]][trunk_l1[1]]['probe']))
                    trunk_l0_res = helper(g, trunk_l0, t)
                    trunk_l1_res = helper(g, trunk_l1, t)
                    if trunk_l0_res == NEG and trunk_l1_res == NEG:
                        g[l[0]][l[1]]['inference'][t] = SURE
                        call_depth.pop()
                        return SURE
                    else:
                        g[l[0]][l[1]]['inference'][t] = NEG
                        call_depth.pop()
                        return NEG
        # 5/ both side has no extension branch, i.e standalone link
        elif len(ext[l[1]]) == 0 and len(ext[l[0]]) == 0:
            g[l[0]][l[1]]['inference'][t] = SURE
            call_depth.pop()
            return SURE
        # 4/ one side has no extension branch
        elif len(ext[l[0]]) == 0:
            if ext_con_count_prop[l[1]] > 1:
                g[l[0]][l[1]]['inference'][t] = SURE
                call_depth.pop()
                return SURE
            elif len(ext[l[1]]) == 1:
                if ext[l[1]][0][1] == ext[l[1]][0][2]:
                    g[l[0]][l[1]]['inference'][t] = LIKELY
                    call_depth.pop()
                    return LIKELY
                else:  # ext[l[1]][0][1] > ext[l[1]][0][2]:
                    if ext_con_count_abs[l[1]] < 1:
                        g[l[0]][l[1]]['inference'][t] = SURE
                        call_depth.pop()
                        return SURE
                    else:
                        trunk = (l[1], ext[l[1]][0][0])  # the only extension branch on l[1]
                        logging.debug("Dependence chain: %s, %r -> %r" % (tt.epoch_to_string(t), l, trunk))
                        trunk_res = helper(g, trunk, t)
                        if trunk_res == NEG:
                            g[l[0]][l[1]]['inference'][t] = SURE
                            call_depth.pop()
                            return SURE
                        else:
                            g[l[0]][l[1]]['inference'][t] = NEG
                            call_depth.pop()
                            return NEG
        elif len(ext[l[1]]) == 0:
            if ext_con_count_prop[l[0]] > 1:
                g[l[0]][l[1]]['inference'][t] = SURE
                call_depth.pop()
                return SURE
            elif len(ext[l[0]]) == 1:
                if ext[l[0]][0][1] == ext[l[0]][0][2]:
                    g[l[0]][l[1]]['inference'][t] = LIKELY
                    call_depth.pop()
                    return LIKELY
                else:  # ext[l[0]][0][1] > ext[l[0]][0][2]:
                    if ext_con_count_abs[l[0]] < 1:
                        g[l[0]][l[1]]['inference'][t] = SURE
                        call_depth.pop()
                        return SURE
                    else:
                        trunk = (l[0], ext[l[0]][0][0])  # the only extension branch on l[1]
                        logging.debug("Dependence chain: %s, %r -> %r" % (tt.epoch_to_string(t), l, trunk))
                        trunk_res = helper(g, trunk, t)
                        if trunk_res == NEG:
                            g[l[0]][l[1]]['inference'][t] = SURE
                            call_depth.pop()
                            return SURE
                        else:
                            g[l[0]][l[1]]['inference'][t] = NEG
                            call_depth.pop()
                            return NEG
        else:
            g[l[0]][l[1]]['inference'][t] = NEG
            call_depth.pop()
            return NEG

    t1 = time.time()

    for ts in range((begin // bin_size) * bin_size, ((stop // bin_size) + 1) * bin_size, bin_size):
        for link in graph.edges_iter():
            if graph[link[0]][link[1]]['score'][ts] > link_threshold and ts not in graph[link[0]][link[1]]['inference']:
                graph[link[0]][link[1]]['inference'][ts] = helper(graph, link, ts)
    t2 = time.time()
    logging.debug("Link congestion inference in %.2f sec" % (t2 - t1))


def find_branches(graph, n1, n2):
    """ find all the links sharing nodes with the given link (n1, n2)
    Args:
        graph (nx.Graph)
        n1 (int): one node of the link
        n2 (int): the other node of the link
    Returns:
        dict{n1: [(x, probe # on (n1,x), common pb # with (n1, n2))...], n2: []}
        empty dict in the case (n1, n2) is not an edge in graph
    """
    try:
        pbs = set(graph.edge[n1][n2]['probe'])
    except KeyError:
        return {n1: [], n2: []}
    res = {n1: [], n2: []}
    for tup in [(n1, n2), (n2, n1)]:
        n, other = tup
        for neighbour in graph.neighbors(n):
            if neighbour != other:
                n_pbs = set(graph.edge[n][neighbour]['probe'])
                common = n_pbs & pbs
                res[n].append((neighbour, len(n_pbs), len(common)))
    return res


def divergent_set(l, crosspoints):
    """ find largest subsets of l so that only common part among any elements in the subset is those in the crosspoints

    Args:
        l (dict): {element: set(attributes),...}
        crosspoints (set): set of attributes allowed for being in common

    Return:
        tuple (the size of subset, {'member':[keys of l], 'attr': union of member attributes})
    """

    def ok(o, target):
        """test if intersection between o and target is equal to crosspoints"""
        if set.intersection(target, o) == set(crosspoints):
            return True
        else:
            return False

    # source https://stackoverflow.com/questions/10823227/how-to-get-all-the-maximums-max-function
    def maxes(a, key=None):
        """return all the i with the maximum of key(i) for i in a"""
        if key is None:
            key = lambda x: x
        m, max_list = key(a[0]), []
        for s in a:
            k = key(s)
            if k > m:
                m, max_list = k, [s]
            elif k == m:
                max_list.append(s)
        return m, max_list

    candidate = []

    # TODO: not all possible combination is tested; it is in fact a maximum clique problem NP-complete
    for e in l:
        for c in candidate:
            if ok(l[e], c['attr']):
                c['member'].append(e)
                c['attr'] |= l[e]
        candidate.append({"member": [e], "attr": set(l[e])})

    return maxes(candidate, key=lambda a: len(a['member']))



