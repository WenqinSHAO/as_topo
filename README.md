# What is it about?
This project visualizes the RIPE traceroute measurements collected in [a previous project](https://github.com/WenqinSHAO/rtt.git)
on RTT change detection and correlation with path changes.

![Screenshot of the visualization interface](./screenshot.gif)

RIPE Atlas recently released a visual tool [TraceMON](https://labs.ripe.net/Members/massimo_candela/tracemon-traceroute-visualisation-network-debugging-tool)
for their traceroute measurements.
However it only allows a handful probes to be visualized at a time.
With the tools provided in this work, we are able to quickly and interactively
plot and query the AS-level topology learnt from traceroutes initiated by more than 6000 RIPE Atlas probes toward DNS b-root.

# How to use?
1. Generate a topology graph from paths measured by traceroute;
2. visualize the generated graph in an interactive manner.

## From paths to topology graph
Traceroute measurements from RIPE Atlas are the input to this project.
Tools are built previously to translate IP hops to AS hops.
The presence of IXP is as well detected.
The data format of processed RIPE traceroute measurement is specified in the [docs](https://github.com/WenqinSHAO/rtt/blob/master/docs/path_analysis.md#output)
of the previous project.

For the moment being, this work focuses on the topology visualization at AS level.
Therefore, [as_graph.py](./as_graph.py) reads the __asn_path__ attribute of each probe
in building the topology graph.

More detailed usage:
```
$ python as_graph.py -h
usage: as_graph.py [-h] [-d DIRECTORY] [-s SUFFIX] [-e END] [-b BEGINTIME]
                   [-t STOPTIME] [-o OUTFILE]

optional arguments:
  -h, --help            show this help message and exit
  -d DIRECTORY, --directory DIRECTORY
                        the directory storing data.
  -s SUFFIX, --suffix SUFFIX
                        the suffix of files to be considered in the directory
  -e END, --end END     if all the measurements have a common destination,
                        specify it with this flag
  -b BEGINTIME, --beginTime BEGINTIME
                        the beginning moment for traceroute rendering, format
                        %Y-%m-%d %H:%M:%S %z
  -t STOPTIME, --stopTime STOPTIME
                        the ending moment for traceroute rendering, format
                        %Y-%m-%d %H:%M:%S %z
  -o OUTFILE, --outfile OUTFILE
                        Specify the name of output .json file

```
Use __-e__ option to specify the destination ASN if it can be known in adavance.
That will help filter out the traceroute measurements failed to reach the destination.
If unspecified, any ASN appears at the end of a path will be regarded as a destination and
plotted in red.

If begin time (__-b__) or stop time (__-t__) is not given,
the script will read from/to the beginning/end of path sequences.
If both of them remain unspecified, only of first traceroute path of each probe will be considered.

An example output of generated topology graph is given in [example.json](./example.json).

## Viusalize in web
This step visualizes in a web browser the above produced .json file describing the graph
of AS topologh revealed by traceroute measurements.

One can directly open [graph.html](./graph.html) in his favorite browser for that purpose.
(NOTE: code only tested with Chrome and Safari.)

One can also select and visualize .json files locally available.
At the bottom of the page, we provide as well the parameters fed to [as_graph.py](./as_graph.py)
in building the graph.

Red nodes are measurement destinations, orange nodes are IXPs, violet ones are source ASes
of traceroutes, remaining transit ASes are in green.

Hover the mouse over nodes will show their ASN.
When placing mouse over links, the IDs of probe that ever passes through this link will be shown.
By double clicking on the link, these probe IDs are save to a file.

Single click on a source node will shown all the links that all its probes took to reach the destinations.

# Requirements
Python library [networkX](https://networkx.github.io) is required in building the topology graph.

[d3](https://d3js.org), [FileSaver](https://github.com/eligrey/FileSaver.js.git), [lodash](https://lodash.com) is
required by the [js_lib/vis.js](./js_lib/vis.js).