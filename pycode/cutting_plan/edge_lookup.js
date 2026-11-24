(() => {
  const catalog = {{EDGE_CATALOG}};
  const fold = value => String(value || '').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]/g, '');
  const meanings = {N: 'Nincs élzárás', FE: 'FE gyártási jelölés', '1H': 'Egy hosszú oldal', '2H': 'Két hosszú oldal', '1R': 'Egy rövid oldal', '2R': 'Két rövid oldal', '1H1R': 'Egy hosszú és egy rövid oldal', '1H2R': 'Egy hosszú és két rövid oldal', '2H1R': 'Két hosszú és egy rövid oldal', '2H2R': 'Mind a négy oldal'};
  const knownSizes = Object.entries(catalog.sizes).map(([key, records]) => ({dims: key.split('x').map(Number), records}));
  window.cuttingEdgeLookup = (width, height, colour = '') => {
    const dims = [Number(width), Number(height)];
    if (!dims.every(n => Number.isInteger(n) && n > 0)) return {status: 'missing', label: '', title: ''};
    dims.sort((a,b) => a-b);
    const explicitSize = (catalog.sizeAliases || {})[dims.join('x')];
    const records = catalog.sizes[(explicitSize || dims).join('x')] || [];
    const name = catalog.aliases[fold(colour)] || fold(colour);
    const manual = records.filter(row => row.manual && (!row.colour || row.colour === name));
    const sameColour = name ? records.filter(row => row.colour === name) : [];
    let candidates = manual.length ? manual : sameColour.length ? sameColour : records;
    let approximate = !!explicitSize, matchedSizes = explicitSize ? [explicitSize] : [];
    if (!records.length && !explicitSize) {
      let nearby = knownSizes.filter(size => size.dims.every((n, i) => Math.abs(n-dims[i]) <= 3));
      const coloured = name ? nearby.flatMap(size => {const rows=size.records.filter(row=>row.colour===name);return rows.length?[{...size, records: rows}]:[];}) : [];
      if (coloured.length) nearby = coloured;
      if (nearby.length) {
        const distance = size => size.dims.reduce((sum,n,i)=>sum+(n-dims[i])**2,0);
        const closest = Math.min(...nearby.map(distance));
        const nearest = nearby.filter(size => distance(size) === closest);
        candidates = nearest.flatMap(size => size.records); matchedSizes = nearest.map(size => size.dims);
        approximate = true;
      }
    }
    const matchNote = approximate ? `Közelítő méret: ${dims.join(' × ')} → ${matchedSizes.map(size=>size.join(' × ')).join(' / ')} mm. ` : '';
    const codes = [...new Set(candidates.map(row => row.edge))].sort();
    if (codes.length === 1) return {status: 'matched', approximate, matchedSizes, code: codes[0], label: `${approximate ? '≈ ' : ''}${codes[0]}`, title: `${matchNote}Élzárás: ${codes[0]} · ${meanings[codes[0]] || codes[0]}`};
    if (!codes.length) return {status: 'unknown', approximate, matchedSizes, label: 'Nincs adat', title: `${matchNote}Ehhez a mérethez nincs ismert élzárási adat.`};
    const details = [...new Set(candidates.map(row => `${row.edge}: ${row.descriptions.join(', ') || meanings[row.edge] || ''}`))];
    return {status: 'ambiguous', approximate, matchedSizes, label: 'Ellenőrizd', title: `${matchNote}Többféle élzárás (${codes.join(' / ')}). Az alkatrész alapján ellenőrizendő. ${details.join('; ')}`};
  };
  window.cuttingUpdateEdgeBadge = (badge, width, height, colour) => {
    const result = window.cuttingEdgeLookup(width, height, colour);
    badge.hidden = result.status === 'missing'; badge.dataset.status = result.status;
    badge.dataset.approximate = String(!!result.approximate);
    badge.textContent = result.label; badge.title = result.title;
    badge.setAttribute('aria-label', result.title);
  };
  window.cuttingEdgeBadge = (width, height, colour) => {
    const badge = document.createElement('small'); badge.className = 'cp-edge-tag';
    window.cuttingUpdateEdgeBadge(badge, width, height, colour); return badge;
  };
})();
