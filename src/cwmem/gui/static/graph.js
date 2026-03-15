/* cwmem GUI — Cytoscape.js graph visualization */

let cy = null;

/* Sapphire palette — comma-separated HSL for Cytoscape compatibility */
const NODE_COLORS = {
  entry: '#2563eb',     /* blue-500 */
  event: '#36997a',     /* secondary-green-2 */
  entity: '#b85c3b',    /* secondary-copper-2 */
};

const NODE_BORDER = {
  entry: '#003580',     /* blue-900 */
  event: '#1a5c3d',     /* secondary-green-1 */
  entity: '#6e3219',    /* secondary-copper-1 */
};

/* Current layout settings (mutable from UI) */
const layoutSettings = {
  nodeRepulsion: 80000,
  idealEdgeLength: 120,
  gravity: 0.08,
  componentSpacing: 150,
};

function renderGraph(data) {
  const container = document.getElementById('cy');
  const elements = buildElements(data);

  if (cy) cy.destroy();

  cy = cytoscape({
    container: container,
    elements: elements,
    style: [
      {
        selector: 'node',
        style: {
          'label': 'data(label)',
          'background-color': '#ffffff',
          'border-color': 'data(color)',
          'border-width': 2.5,
          'color': '#0f172a',
          'text-valign': 'bottom',
          'text-halign': 'center',
          'font-size': '9px',
          'font-family': 'Plus Jakarta Sans, sans-serif',
          'text-margin-y': 8,
          'text-max-width': '110px',
          'text-wrap': 'ellipsis',
          'width': 20,
          'height': 20,
          'text-background-color': 'rgba(255, 255, 255, 0.85)',
          'text-background-opacity': 0.85,
          'text-background-padding': '4px',
          'text-background-shape': 'roundrectangle',
        },
      },
      {
        selector: 'node.root',
        style: {
          'width': 28,
          'height': 28,
          'border-width': 2.5,
          'border-color': '#f59e0b',
          'font-size': '9px',
          'font-weight': 'bold',
          'color': '#002347',
          'z-index': 10,
        },
      },
      {
        selector: 'node.entity',
        style: {
          'shape': 'diamond',
        },
      },
      {
        selector: 'node.event',
        style: {
          'shape': 'round-triangle',
        },
      },
      {
        selector: 'edge',
        style: {
          'label': 'data(label)',
          'width': 'data(width)',
          'font-family': 'JetBrains Mono, monospace',
          'letter-spacing': '0.5px',
          'font-family': 'JetBrains Mono, monospace',
          'letter-spacing': '0.5px',
          'font-family': 'JetBrains Mono, monospace',
          'letter-spacing': '0.5px',
          'line-color': '#cbd5e1',
          'target-arrow-color': '#cbd5e1',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 0.6,
          'curve-style': 'bezier',
          'font-size': '9px',
          'color': '#64748b',
          'text-rotation': 'autorotate',
          'text-margin-y': -6,
          'text-background-color': 'rgba(255, 255, 255, 0.85)',
          'text-background-opacity': 0.85,
          'text-background-padding': '1px',
          'text-background-shape': 'roundrectangle',
          'opacity': 0.7,
        },
      },
      {
        selector: 'edge.inferred',
        style: {
          'line-style': 'dashed',
          'line-dash-pattern': [4, 4],
          'line-color': '#ced6de',
          'target-arrow-color': '#ced6de',
          'opacity': 0.5,
          'label': '',
        },
      },
      {
        selector: 'node:active',
        style: {
          'overlay-color': '#2563eb',
          'overlay-opacity': 0.05,
        },
      },
      {
        selector: 'node.highlight',
        style: {
          'border-width': 4,
          'border-color': '#f59e0b',
          'color': '#002347',
          'font-weight': 'bold',
          'z-index': 10,
        },
      },
      {
        selector: 'edge.highlight',
        style: {
          'line-color': '#2563eb',
          'target-arrow-color': '#2563eb',
          'opacity': 1,
          'width': 2,
        },
      },
      {
        selector: 'node.dimmed',
        style: {
          'opacity': 0.25,
        },
      },
      {
        selector: 'edge.dimmed',
        style: {
          'opacity': 0.08,
        },
      },
    ],
    layout: buildLayout(elements),
    wheelSensitivity: 0.25,
    minZoom: 0.3,
    maxZoom: 3,
    pixelRatio: 'auto',
  });

  // Hover: highlight connected nodes
  cy.on('mouseover', 'node', function(evt) {
    const node = evt.target;
    const neighborhood = node.closedNeighborhood();
    cy.elements().addClass('dimmed');
    neighborhood.removeClass('dimmed');
    node.addClass('highlight');
    node.connectedEdges().addClass('highlight');
  });

  cy.on('mouseout', 'node', function() {
    cy.elements().removeClass('dimmed highlight');
  });

  // Click node -> show detail
  cy.on('tap', 'node', async function(evt) {
    const node = evt.target;
    const resourceId = node.data('id');
    try {
      const data = await api('/resources/' + encodeURIComponent(resourceId));
      showGraphDetail(data);
    } catch {
      showGraphDetail({
        resource: node.data(),
        kind: node.data('type'),
        label: node.data('label'),
        summary: '',
      });
    }
  });

  // Double-click node -> re-center graph
  cy.on('dbltap', 'node', function(evt) {
    const nodeId = evt.target.data('id');
    document.getElementById('graph-id').value = nodeId;
    loadGraph();
  });

  // Click background -> hide detail
  cy.on('tap', function(evt) {
    if (evt.target === cy) {
      document.getElementById('graph-detail').classList.add('hidden');
    }
  });
}

function buildLayout(elements) {
  const nodeCount = elements.nodes ? elements.nodes.length : 0;
  return {
    name: 'cose',
    animate: true,
    animationDuration: 800,
    animationEasing: 'ease-out',
    nodeRepulsion: function() { return layoutSettings.nodeRepulsion + nodeCount * 3000; },
    idealEdgeLength: function(edge) {
      return edge.hasClass('inferred')
        ? layoutSettings.idealEdgeLength * 1.7
        : layoutSettings.idealEdgeLength;
    },
    edgeElasticity: function(edge) { return edge.hasClass('inferred') ? 200 : 45; },
    gravity: layoutSettings.gravity,
    numIter: 3000,
    padding: 60,
    nodeOverlap: 50,
    nestingFactor: 1.2,
    randomize: true,
    componentSpacing: layoutSettings.componentSpacing,
    coolingFactor: 0.99,
    initialTemp: 400,
  };
}

function rerunLayout() {
  if (!cy) return;
  const layout = cy.layout(buildLayout({ nodes: cy.nodes().toArray() }));
  layout.run();
}

function buildElements(data) {
  const nodes = [];
  const edges = [];
  const seen = new Set();

  if (data.root) {
    const r = data.root;
    nodes.push({
      data: {
        id: r.resource_id,
        label: truncLabel(r.label),
        type: r.resource_type,
        color: NODE_COLORS[r.resource_type] || '#2563eb',
        borderColor: NODE_BORDER[r.resource_type] || '#003580',
      },
      classes: 'root ' + (r.resource_type || ''),
    });
    seen.add(r.resource_id);
  }

  if (data.nodes) {
    for (const n of data.nodes) {
      if (seen.has(n.resource_id)) continue;
      seen.add(n.resource_id);
      nodes.push({
        data: {
          id: n.resource_id,
          label: truncLabel(n.label),
          type: n.resource_type,
          color: NODE_COLORS[n.resource_type] || '#2563eb',
          borderColor: NODE_BORDER[n.resource_type] || '#003580',
        },
        classes: n.resource_type || '',
      });
    }
  }

  if (data.edges) {
    for (const e of data.edges) {
      if (!seen.has(e.source_id) || !seen.has(e.target_id)) continue;
      const w = 0.8 + e.confidence * 1.2;
      edges.push({
        data: {
          id: e.public_id || (e.source_id + '-' + e.target_id + '-' + e.relation_type),
          source: e.source_id,
          target: e.target_id,
          label: e.relation_type,
          width: w,
        },
        classes: e.is_inferred ? 'inferred' : '',
      });
    }
  }

  return { nodes, edges };
}

function showGraphDetail(data) {
  const panel = document.getElementById('graph-detail');
  panel.classList.remove('hidden');
  panel.innerHTML = resourceDetailHtml(data.resource, data.kind);
}

function truncLabel(s) {
  if (!s) return '';
  return s.length <= 20 ? s : s.slice(0, 19) + '\u2026';
}
