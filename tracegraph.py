import networkx as nx
from itertools import count, chain
from collections import defaultdict

_attrs = dict(id='id', source='source', target='target', key='key', name='name')


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
                       [(source, mapping[u]), (target, mapping[v])]))
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
        R.add_node(n, d)

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