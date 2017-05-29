// the script is based on https://bl.ocks.org/mbostock/4062045

var container = d3.select('div#container');

var svg = container.select("svg#graph");

svg.attr('width', 5000)
   .attr('height', 5000);

var width = svg.attr('width');
var height = svg.attr('height');

// text box for graph info
var graphinfo = d3.select("pre#graphinfo")

var linktip = d3.select("body").append("div")
                    .attr("class", "linktip")
                    .style("opacity", 0);

var nodetip = d3.select("body").append("div")
                    .attr("class", "nodetip")
                    .style("opacity", 0);

// node color legend:
// 1 for source; 2 for ixp; 3 for dst; 4 for all the others
var color = d3.scaleOrdinal()
        .domain([1,2,3,4])
        .range(["#bebada", "#fdb462", "#e41a1c", "#b3de69"]);

var tparser = d3.utcParse("%Y-%m-%d %H:%M");
var tformatter = d3.utcFormat("%Y-%m-%d %H:%M");

var opened_f, loaded_data, moment, is_congestion_graph, show_inference_result, bin_size, begin, end;

function plot() {
    var file = document.getElementById("file_input");
    if ('files' in file && file.files.length > 0) {
        var f = file.files[0]; // get the first file selected by the file input
        if (f) {
            if (f != opened_f) {
                // only proceed if it differs from the file already opened
                graphinfo.text("Reading data file...");
                var reader = new FileReader();
                reader.onloadend = function(evt) {
                    //var t1 = performance.now();
                    //d3.select("#status").text(Math.round(f.size/(1048576)) + "MB loaded in " + parseFloat(Math.round((t1-t0) * 100) / 100).toFixed(2) + " milliseconds.\n Now scoping and plotting data...");
                    //console.log(f.name + ": " + Math.round(f.size/(1048576)) + "MB, " + parseFloat(Math.round((t1-t0) * 100) / 100).toFixed(2) + "msec");
                    opened_f = f;
                    try {
                        loaded_data = JSON.parse(evt.target.result); // read the file as text and parse it to JSON object
                    } catch (ex) {
                        console.error(ex);
                    }
                    // cannot merge with else clause: see http://stackoverflow.com/questions/13487437/change-global-variable-inside-javascript-closure
                    // event driven not sequential
                    svg.selectAll("*").remove();
                    init();
                };
                //var t0 = performance.now();
                reader.readAsText(f);
            } else {
                //d3.select("#status").text("Scoping and plotting data...");
                //svg.selectAll("*").remove(); // clean the canvas
                update();
            }
        }
    }
}

function init() {

      if (loaded_data.hasOwnProperty("congestion")) {
        is_congestion_graph = loaded_data.congestion;
        //console.log("is congestion graph " + is_congestion_graph);
      } else {
        is_congestion_graph = false
      }

      if (is_congestion_graph) {
          if (loaded_data.graph.hasOwnProperty("cpt_bin_size")) {
            bin_size = loaded_data.graph.cpt_bin_size;
            //console.log("bin size " + bin_size);
          }

          if (loaded_data.graph.hasOwnProperty("congestion_begin")) {
            begin = loaded_data.graph.congestion_begin * 1000;
            //console.log(tformatter(begin));
          }

          if (loaded_data.graph.hasOwnProperty("congestion_end")) {
            end = loaded_data.graph.congestion_end * 1000;
            //console.log(tformatter(end));
          }

          if(! tparser(document.getElementById("datetime").value)) {
            moment = Math.floor(loaded_data.graph.congestion_begin/bin_size) * bin_size * 1000;
            document.getElementById("datetime").value = tformatter(moment);
          }
      }

      show_inference_result = false;

      var simulation = d3.forceSimulation()
            .force("link", d3.forceLink().id(function(d) { return d.id; }))
            .force("charge", d3.forceManyBody())
            .force("center", d3.forceCenter(width / 2, height / 2));

      function dragstarted(d) {
          if (!d3.event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
      }

      function dragged(d) {
          d.fx = d3.event.x;
          d.fy = d3.event.y;
      }

      function dragended(d) {
          if (!d3.event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
      }

      d3.select("#graphinfo").text(JSON.stringify(loaded_data.graph, undefined, 2));

      // add links
      var link = svg.append("g")
            .attr("class", "links")
        .selectAll("line")
        .data(loaded_data.links)
        .enter().append("line")
            .attr("congestion_level", congestion)
            .attr("inference", inference)
            .attr("stroke", linkColor)
            .attr("stroke-width", linkWidth)
            .attr("opacity", linkOpacity)
            .on("dblclick", saveLink)
            .on("mouseover", function(d) {
                linktip.transition()
                    .duration(200)
                    .style("opacity", .7);
                var text = d.probe.length.toString() + " probes on (" + d.src_name+ ", " + d.tgt_name + ")";
                if (is_congestion_graph) {
                    text += '<br>' + 'congestion level: ' + d3.select(this).attr("congestion_level");
                }
                linktip.html(text)
                    .style("left", (d3.event.pageX - 80) + "px")
                    .style("top", (d3.event.pageY - 28) + "px");
            })
            .on("mouseout", function(d) {
                linktip.transition()
                    .duration(200)
                    .style("opacity", 0);
            });

      // add nodes
      var node = svg.append("g")
            .attr("class", "nodes")
        .selectAll("circle")
        .data(loaded_data.nodes)
        .enter().append("circle")
            .attr("r", 6)
            .attr("inference", inference)
            .attr("fill", nodeColor)
            .attr("stroke", nodeBorder)
            .attr("stroke-width", 2)
            .call(d3.drag()
                    .on("start", dragstarted)
                    .on("drag", dragged)
                    .on("end", dragended)
                )
            .on("click", showPath)
            .on("mouseover", function (d) {
                nodetip.transition()
                    .duration(200)
                    .style("opacity", .7);
                var text = d.name;
                if (d.hasOwnProperty('hosting')) {
                    text += "<br> hosting: " + d.hosting.toString();
                }
                nodetip.html(text)
                    .style("left", (d3.event.pageX - 80) + "px")
                    .style("top", (d3.event.pageY - 28) + "px");
            })
            .on("mouseout", function (d) {
                nodetip.transition()
                    .duration(200)
                    .style("opacity", 0);
            });


      simulation
          .nodes(loaded_data.nodes)
          .on("tick", ticked);

      simulation.force("link")
          .links(loaded_data.links);

      function ticked() {
            link
            .attr("x1", function(d) { return d.source.x; })
            .attr("y1", function(d) { return d.source.y; })
            .attr("x2", function(d) { return d.target.x; })
            .attr("y2", function(d) { return d.target.y; });

            node
            .attr("cx", function(d) { return d.x; })
            .attr("cy", function(d) { return d.y; });
      }
}

function update() {
    if (is_congestion_graph) {
        var m =  tparser(document.getElementById("datetime").value);
        m = m ? m : begin;
        moment = Math.floor(m / (bin_size * 1000)) * bin_size * 1000;
        document.getElementById("datetime").value = tformatter(moment);

        svg.selectAll("line")
            .attr("congestion_level", congestion)
            .attr("inference", inference);
        svg.selectAll("line")
            .attr("stroke", linkColor)
            .attr("opacity", linkOpacity);

        svg.selectAll("circle")
            .attr("inference", inference);
        svg.selectAll("circle")
            .attr("stroke", nodeBorder)
    } else {
        alert("Only congestion graph can be navigated in time.");
    }
}

function navigator(is_forward) {
    var m = is_forward? moment + bin_size * 1000 : moment - bin_size * 1000;
    document.getElementById("datetime").value = tformatter(m);
    update();
}

function datetimeSearch(arr, v) {
    // binary search that return arr[i].value with arr[i].epoch == v
    var low = 0;
    var high = arr.length;
    var mid;
    while (low < high) {
        mid = Math.floor((low+high)/2);
        if (arr[mid].epoch * 1000 == v) {
            return arr[mid].value
        }
        if ((arr[mid].epoch * 1000) < v) {
            low = mid + 1;
        } else {
            high = mid;
        }
    }
    return 'NA';
}


// what happens if a link is double clicked
function saveLink(d) {
    var blob = new Blob([d.probe.join('\n')], {type: "text/plain;charset=utf-8"});
    var fn = d.src_name.toString() + '_' + d.tgt_name.toString() + '.txt';
    saveAs(blob, fn);
    alert("IDs of " + d.probe.length.toString() + " probes on (" + d.src_name.toString() + ', ' + d.tgt_name.toString() + " ) saved to file: " + fn);
}

// what happens once a node is clicked
function showPath(d) {
    var n = d3.select(this);
    if (d.hasOwnProperty("hosting")){
        var pb = d.hosting;
        if (!n.classed("show-path")) {
            n.classed("show-path", true)
                .attr("r", 10)
                .attr("fill", nodeColor);
            d3.selectAll('line').each(function (d) {
                for (var i = 0; i < pb.length; i++) {
                    if (d.probe.includes(pb[i])) {
                        d3.select(this)
                            .classed("show-path", true)
                            .attr("stroke", linkColor)
                            .attr("stroke-width", linkWidth)
                            .attr("opacity", linkOpacity);
                        break;
                    }
                }
            });
        } else {
            n.classed("show-path", false)
                .attr("r", 6)
                .attr("fill", nodeColor);
            d3.selectAll('line').each(function (d) {
                for (var i = 0; i < pb.length; i++) {
                    if (d.probe.includes(pb[i])) {
                        d3.select(this)
                            .classed("show-path", false)
                            .attr("stroke", linkColor)
                            .attr("stroke-width", linkWidth)
                            .attr("opacity", linkOpacity);
                        break;
                    }
                }
            });
        }
    }
}

function congestion(d) {
    if(is_congestion_graph){
        return datetimeSearch(d.congestion, moment);
    } else {
        return 'NA';
    }
}

function inference(d) {
    if(is_congestion_graph){
        return datetimeSearch(d.inference, moment);
    } else {
        return 'NA';
    }
}

function nodeColor(d) {
    if (!d3.select(this).classed("show-path")){
        if (d.tag.includes(3)) {
            return color(3); // dst
        } else if (d.tag.includes(2)) {
            return color(2); // ixp
        } else if (d.tag.includes(1)) {
            return color(1); // source
        } else {
            return color(4); // others
        }
    } else {
        return "#4a1486";
    }
}

function linkOpacity(d) {
    if (d3.select(this).classed("show-path")) {
        return 0.9;
    } else {
        if (is_congestion_graph) {
            var level = d3.select(this).attr("congestion_level");
            if (level && level >.1) {
                return .6;
            } else {
                return .1;
            }
        } else {

            return (d.probe.length > 30) ? 0.6: 0.1;
        }
    }
}

function linkWidth(d) {
    if (!d3.select(this).classed("show-path")) {
        return 2 * Math.sqrt(d.probe.length);
    } else {
        return 6 * Math.sqrt(d.probe.length);
    }
}

function linkColor(d) {
    if(is_congestion_graph){
    // case of congestion graph
        if (show_inference_result) {
        // case of show inference result
            var res = d3.select(this).attr("inference");
            if (res == 'true' || res === true) {
                return "#810f7c";
            } else {
                return "#74c476";
            }
        } else {
        // case of congestion index level
            var level = d3.select(this).attr("congestion_level");
            if (level && level > .1) {
                return d3.interpolateReds(level);
            } else {
            return "#999"
            }
        }
    } else {
    // case of naive topo graph
        if (d3.select(this).classed("show-path")) {
        // link selected
            return "#e34a31";
        } else {
        // link not selected
            return "#999";
        }
    }
}

function nodeBorder(d) {
    if (is_congestion_graph) {
        if (show_inference_result) {
            var res = d3.select(this).attr("inference");
            if (res == 'true' || res === true) {
                return "#810f7c";
            } else {
                return "#74c476";
            }
        }
    }
    return "white";
 }



d3.select('body')
    .on("keydown", function (){
        if (d3.event.shiftKey) {
            switch(d3.event.keyCode) {
                case 13:
                    show_inference_result = show_inference_result? false: true;
                    update();
                    break;
                case 39:
                    navigator(true);
                    break;
                case 37:
                    navigator(false);
                    break;
                default:
                    break;
            }
        } else if (d3.event.keyCode == 13){
            plot();
        }
    });

d3.select("input#previous")
    .on("click", function() {
        d3.event.stopPropagation();
        d3.event.preventDefault();
        navigator(false);
        return false;
    });

d3.select("input#next")
    .on("click", function() {
        d3.event.stopPropagation();
        d3.event.preventDefault();
        navigator(true);
        return false;
    });