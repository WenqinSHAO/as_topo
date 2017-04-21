var svg = d3.select("svg"),
    width = +svg.attr("width"),
    height = +svg.attr("height");

var color = d3.scaleOrdinal()
    .domain([1,2,3,4])
    .range(["#bebada", "#fdb462", "#e41a1c", "#b3de69"]);

var simulation = d3.forceSimulation()
    .force("link", d3.forceLink().id(function(d) { return d.id; }))
    .force("charge", d3.forceManyBody())
    .force("center", d3.forceCenter(width / 2, height / 2));

var toggle = 0

d3.json("graph.json", function(error, graph) {
  if (error) throw error;

  var link = svg.append("g")
      .attr("class", "links")
    .selectAll("line")
    .data(graph.links)
    .enter().append("line")
      .attr("stroke-width", function(d) { return 2 * Math.sqrt(d.probe.length); });

  var node = svg.append("g")
      .attr("class", "nodes")
    .selectAll("circle")
    .data(graph.nodes)
    .enter().append("circle")
      .attr("r", 6)
      .attr("fill", function(d) { return color(d.termination); })
      .call(d3.drag()
          .on("start", dragstarted)
          .on("drag", dragged)
          .on("end", dragended))
       .on("mouseover", mouseOver)
       .on("mouseout", mouseOut);

  node.append("title")
      .text(function(d) {
          if (_.has(d, 'hosting')) {
              return 'AS '+d.name + ' hosting:\n' + d.hosting.toString();
              }
          else {
              return 'AS '+d.name;
              }
       });

  link.append("title")
      .text(function(d) {
          return d.probe.length.toString() + ' probes on (' + d.src_name+ ', ' + d.tgt_name + ')\n' + '[' + d.probe.toString() + ']'; });

  simulation
      .nodes(graph.nodes)
      .on("tick", ticked);

  simulation.force("link")
      .links(graph.links);

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

  function mouseOver(d, i) {
    d3.select(this)
      .attr("r", 10);
    if (d.termination == 1){
        d3.select(this)
          .attr("fill", "#4a1486");
        var pb = d.hosting;
        d3.selectAll('line').each(function (d) {
            for (var i = 0; i < pb.length; i++) {
                if (d.probe.includes(pb[i])){
                    d3.select(this)
                      .style("stroke", "#e34a33")
                      .style("opacity", .8)
                      .attr("stroke-width", function(d) { return 6 * Math.sqrt(d.probe.length); });
                    break;
                }
            }
        });
    }
  }

  function mouseOut(d, i) {
    d3.select(this)
      .attr("r", 6);
    if (d.termination == 1){
        d3.select(this)
          .attr("fill", function(d) {return color(d.termination); });
        d3.selectAll('line')
          .style("stroke", "#999")
          .style("opacity", 0.6)
          .attr("stroke-width", function(d) { return 2 * Math.sqrt(d.probe.length); });
        }
    }

});

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
