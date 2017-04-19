import networkx as nx
from itertools import count, chain
from collections import defaultdict

_attrs = dict(id='id', source='source', target='target', key='key', name='name')


def path_to_graph(paths, probe, g):
    for p in paths:
        for e in zip(p[:-1], p[1:]):
            if e not in g.edges():
                g.add_edge(e[0], e[1], probe=set([]))
            g[e[0]][e[1]]['probe'].add(probe)


def node_link_data_modify(G, attrs=_attrs):
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
    if not G.is_multigraph() == H.is_multigraph() == False:
        raise nx.NetworkXError('Doesn\'t handle multi-graph.')

    R = nx.Graph()

    for n, d in chain(G.nodes_iter(data=True), H.nodes_iter(data=True)):
        R.add_node(n, d)


    for src, tgt, d in chain(H.edges_iter(data=True), G.edges_iter(data=True)):
        if (src, tgt) in R.edges_iter():
            dd = defaultdict(list)
            d1 = R[src][tgt]
            for di in (d1, d):
                for k, v in di.iteritems():
                    dd[k].extend(v)
        else:
            dd = d
        R.add_edge(src, tgt, dd)

    return R


def compose_all_modify(graphs):
    graphs = iter(graphs)
    C = next(graphs)
    for H in graphs:
        C = compose_modify(C, H)
    return C