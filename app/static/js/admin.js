/* admin.js - extracted from admin.html
   Handles sidebar nav, map markers, fleet map, webhook simulators,
   and live socket connections. Also lazy-loads Leaflet and Socket.IO. */
"use strict";

// ---- Toast notification helper ----
function showToast(msg) {
    const box = document.getElementById('toast-container') || (() => {
        const d = document.createElement('div');
        d.id = 'toast-container';
        d.style.cssText = 'position:fixed;top:80px;right:16px;z-index:1080;max-width:320px;';
        document.body.appendChild(d);
        return d;
    })();
    const t = document.createElement('div');
    t.className = 'sg-toast success';
    t.innerHTML = msg;
    box.appendChild(t);
    setTimeout(() => t.remove(), 8000);
}

// ---- Sidebar nav: scroll-to-section + active highlight on click ----
document.addEventListener('DOMContentLoaded', () => {
    const navLinks = document.querySelectorAll('#admin-pills a[data-section]');
    const allSections = document.querySelectorAll('.admin-section');

    function hideAllSections() {
        allSections.forEach(s => s.classList.remove('active'));
    }

    function setActive(sectionId) {
        hideAllSections();
        navLinks.forEach(link => {
            if (link.dataset.section === sectionId) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
        const targetEl = document.getElementById(sectionId);
        if (targetEl) {
            targetEl.classList.add('active');
            // Lazy-init Leaflet maps once their section becomes visible — the
            // IntersectionObserver below never fires for display:none sections.
            if (sectionId === 'gis-section') initMaps();
            if (sectionId === 'fleet-section') { initFleetMap(); loadFleetLocations(); }
            if (sectionId === 'sensor-fault-section') { loadSensorFaults(); loadMaintenance(); }
            const yOffset = -100;
            const y = targetEl.getBoundingClientRect().top + window.pageYOffset + yOffset;
            window.scrollTo({ top: y, behavior: 'smooth' });
            // Leaflet needs a size recalculation after display:none -> block.
            setTimeout(() => {
                if (sectionId === 'gis-section' && map) map.invalidateSize();
                if (sectionId === 'fleet-section' && fleetMap) fleetMap.invalidateSize();
            }, 60);
        }
    }

    // Expose for the mobile section jumper (<select onchange=setActive(...)>).
    window.setActive = setActive;

    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.dataset.section;
            setActive(targetId);
        });
    });

    const sectionIds = Array.from(navLinks).map(l => l.dataset.section);
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                setActive(entry.target.id);
            }
        });
    }, { rootMargin: '-80px 0px -60% 0px', threshold: 0 });

    sectionIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) observer.observe(el);
    });

    // Show first section by default
    if (sectionIds.length > 0 && allSections.length > 0) {
        setActive(sectionIds[0]);
    }
});

// ---- Dynamic asset loader (for lazy-loading Leaflet & Socket.IO) ----
function loadScript(url) {
    return new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${url}"]`)) return resolve();
        const s = document.createElement('script');
        s.src = url;
        s.async = true;
        s.onload = () => resolve();
        s.onerror = () => reject(new Error('Failed to load ' + url));
        document.head.appendChild(s);
    });
}

function loadCSS(url) {
    return new Promise((resolve, reject) => {
        if (document.querySelector(`link[href="${url}"]`)) return resolve();
        const l = document.createElement('link');
        l.rel = 'stylesheet';
        l.href = url;
        l.onload = () => resolve();
        l.onerror = () => reject(new Error('Failed to load ' + url));
        document.head.appendChild(l);
    });
}

const LEAFLET_JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
const SOCKET_IO_JS = 'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.min.js';
const LEAFLET_CLUSTER_JS = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js';
const LEAFLET_CLUSTER_CSS = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css';
const LEAFLET_CLUSTER_DEFAULT_CSS = 'https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css';

let leafletLoaded = false;
async function ensureLeafletAndSocket() {
    if (leafletLoaded) return;
    await loadScript(LEAFLET_JS);
    // Marker clustering: dense wards collapse hundreds of circle markers into
    // count bubbles. Best-effort — a failed CDN fetch degrades to individual
    // markers instead of breaking the map.
    try {
        await loadCSS(LEAFLET_CLUSTER_CSS);
        await loadCSS(LEAFLET_CLUSTER_DEFAULT_CSS);
        await loadScript(LEAFLET_CLUSTER_JS);
    } catch (e) {
        console.warn('MarkerCluster unavailable, using individual markers:', e);
    }
    // base.html already loads socket.io on every page — don't fetch it twice.
    if (typeof io === 'undefined') {
        await loadScript(SOCKET_IO_JS);
    }
    leafletLoaded = true;
}

// ---- Application state ----
let smartBins = [];
let currentBinHwId = null;
let map = null;
let binMarkers = {};
let binCluster = null;
let currentRouteLine = null;
let fleetMap = null;
let fleetMarkers = [];

// Fetch smart bins (unchanged API usage)
fetch('/api/bins')
    .then(r => r.json())
    .then(data => { smartBins = data; if (map) buildBinMarkers(); })
    .catch(e => console.error('Bin data load failed:', e));

// ---- Map initialization deferred until Leaflet is loaded ----
function getMarkerColor(status) {
    if (status === 'Critical') return '#E74C3C';
    if (status === 'Warning') return '#F1C40F';
    return '#2ECC71';
}

function buildBinMarkers() {
    if (!map) return;
    binMarkers = {};
    // Cluster dense wards into count bubbles when the plugin loaded; fall
    // back to individual markers otherwise (same visual per-bin behavior).
    const useCluster = typeof L.markerClusterGroup === 'function';
    if (useCluster && binCluster) { map.removeLayer(binCluster); binCluster = null; }
    if (useCluster) binCluster = L.markerClusterGroup({ maxClusterRadius: 45 });
    smartBins.forEach(bin => {
        const marker = L.circleMarker([bin.latitude, bin.longitude], {
            radius: 8,
            fillColor: getMarkerColor(bin.status),
            color: '#FFFFFF',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.9
        });
        if (useCluster && binCluster) binCluster.addLayer(marker); else marker.addTo(map);

        marker.on('click', () => {
            document.getElementById('modalBinId').innerText = bin.hardware_id;
            document.getElementById('modalWard').innerText = bin.ward;
            document.getElementById('modalFillLevel').innerText = `${bin.level}%`;
            document.getElementById('modalBattery').innerText = `${bin.battery}%`;
            document.getElementById('modalTemp').innerText = `${bin.temperature}°C`;
            document.getElementById('modalMethane').innerText = `${bin.methane} ppm`;

            const badge = document.getElementById('modalStatusBadge');
            badge.innerText = bin.status;
            badge.className = 'badge ' + (bin.status === 'Critical' ? 'bg-danger' : (bin.status === 'Warning' ? 'bg-warning text-dark' : 'bg-success'));

            currentBinHwId = bin.hardware_id;
            const compSwitch = document.getElementById('modalCompactorSwitch');
            const compLabel = document.getElementById('modalCompactor');
            compSwitch.checked = bin.precompaction_enabled;
            compLabel.innerText = bin.precompaction_enabled ? 'Enabled' : 'Disabled';

            const myModal = new bootstrap.Modal(document.getElementById('telemetryModal'));
            myModal.show();
        });

        binMarkers[bin.hardware_id] = marker;
    });
    if (useCluster && binCluster) binCluster.addTo(map);
}

function updateBinMarker(bin) {
    const marker = binMarkers[bin.hardware_id];
    if (!marker || !bin) return;
    marker.setStyle({ fillColor: getMarkerColor(bin.status) });
    marker.setLatLng([bin.latitude, bin.longitude]);
}

async function initMaps() {
    if (!leafletLoaded) await ensureLeafletAndSocket();
    if (!map) {
        map = L.map('gisMap').setView([18.0675, 83.4094], 14);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);
        const depotIcon = L.divIcon({
            html: '<div style="background:#2C3E50; width:14px; height:14px; border-radius:50%; border:2px solid white; box-shadow:0 0 10px rgba(0,0,0,0.5);"></div>',
            className: 'depot-icon',
            iconSize: [14, 14]
        });
        L.marker([18.0675, 83.4094], {icon: depotIcon}).bindPopup("<b>Municipal Headquarters Depot</b>").addTo(map);
        if (smartBins && smartBins.length) buildBinMarkers();
    }
    // Initialize fleet map separately
    if (!fleetMap) initFleetMap();
    // Connect live socket once scripts are loaded
    connectLive();
}

// Toggle compactor
async function toggleCompactor() {
    if (!currentBinHwId) return;
    const sw = document.getElementById('modalCompactorSwitch');
    const label = document.getElementById('modalCompactor');
    try {
        const res = await fetch('/admin/toggle-compactor/' + currentBinHwId, {
            method: 'POST',
            headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
        });
        const data = await res.json();
        if (!data.success) throw new Error('toggle failed');
        const enabled = data.precompaction_enabled;
        label.innerText = enabled ? 'Enabled' : 'Disabled';
        const bin = smartBins.find(b => b.hardware_id === currentBinHwId);
        if (bin) bin.precompaction_enabled = enabled;
    } catch (e) {
        alert('Could not toggle solar compactor: ' + e.message);
        sw.checked = !sw.checked;
    }
}

// TSP route optimizer caller (nearest-neighbour + 2-opt on the server)
async function executeRoutingDispatch() {
    const btn = document.getElementById('optimizeBtn');
    const originalLabel = btn ? btn.innerHTML : '';
    if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Optimizing…'; }
    try {
        // Ensure the GIS map is ready so we can draw the route on it.
        // (setActive already lazy-inits maps; await a tick so that init lands.)
        if (!map) {
            setActive('gis-section');
            await new Promise(r => setTimeout(r, 120));
        }
        if (!map) await initMaps();
        const response = await fetch('/api/route-optimize');
        if (!response.ok) { showToast('⚠️ Routing service unavailable.'); return; }
        const data = await response.json();
        const emptyEl = document.getElementById('routingEmpty');
        const infoBanner = document.getElementById('routingInfo');
        if (emptyEl) emptyEl.classList.add('d-none');
        if (infoBanner) infoBanner.classList.remove('d-none');

        const stops = (data.route || []).filter(n => n.label && n.label !== 'Municipal HQ (Depot)');
        if (!stops.length) {
            // No critical bins today — show a helpful empty state instead of nothing.
            if (currentRouteLine) { map.removeLayer(currentRouteLine); currentRouteLine = null; }
            document.getElementById('routeCount').innerText = '0';
            document.getElementById('routeDistance').innerText = '0 km';
            document.getElementById('routeCo2').innerText = '0 kg';
            document.getElementById('routeFuel').innerText = '₹0';
            document.getElementById('routeHours').innerText = '0 h';
            document.getElementById('routePathText').innerText = '✅ All bins within safe levels — no route needed today.';
            document.getElementById('routeStatsText').innerText = data.message || 'Run the telemetry simulator to create hotspots.';
            return;
        }

        if (currentRouteLine) { map.removeLayer(currentRouteLine); }
        const coords = data.route.map(node => [node.lat, node.lon]);
        currentRouteLine = L.polyline(coords, { color: '#2C3E50', weight: 5, opacity: 0.75, dashArray: '10, 10' }).addTo(map);
        map.fitBounds(currentRouteLine.getBounds());

        document.getElementById('routeCount').innerText = data.critical_count ?? stops.length;
        document.getElementById('routeDistance').innerText = `${data.total_distance || 0} km`;
        document.getElementById('routeCo2').innerText = `${data.co2_saved_kg || 0} kg`;
        document.getElementById('routeFuel').innerText = `₹${data.fuel_saved_rs || 0}`;
        document.getElementById('routeHours').innerText = `${data.manpower_saved_hours || data.manpower_hours || 0} h`;
        const labels = data.route.map(node =>
            node.label === 'Municipal HQ (Depot)'
                ? node.label
                : (node.overflow_eta_hours != null
                    ? `${node.label} (⏳${node.overflow_eta_hours}h)`
                    : node.label)
        );
        document.getElementById('routePathText').innerHTML =
            `<b>Sequenced Pickups Route:</b> ${labels.join(' ➔ ')}`;
        document.getElementById('routeStatsText').innerHTML =
            `Optimized with <code>${data.optimized_with || 'auto'}</code>`;
        showToast(`✅ <strong>Route Optimized!</strong> ${stops.length} bins, ${data.total_distance || 0} km · 🌿 ${data.co2_saved_kg || 0} kg CO₂ · ⛽ ₹${data.fuel_saved_rs || 0} fuel saved`);
    } catch (e) {
        console.error('Route optimize failed:', e);
        showToast('⚠️ Could not optimize route: ' + e.message);
    } finally {
        if (btn) { btn.disabled = false; btn.innerHTML = originalLabel; }
    }
}

async function simulateAnomalyTrigger() {
    // Seeded as BIN-EMG-302 (kept distinct from the generated BIN-3xx scheme).
    // Make sure the map is up even if the user lands here without visiting GIS first,
    // and that bin telemetry has loaded (the initial /api/bins fetch is async).
    if (!map) await initMaps();
    if (!smartBins.length) {
        try {
            const res = await fetch('/api/bins');
            if (!res.ok) throw new Error('HTTP ' + res.status);
            smartBins = await res.json();
            if (map && smartBins.length) buildBinMarkers();
        } catch (e) {
            console.error('Bin data load failed:', e);
        }
    }
    const criticalBin = smartBins.find(b => b.hardware_id === "BIN-EMG-302") ||
                        smartBins.find(b => b.status === "Critical");
    if (criticalBin && binMarkers[criticalBin.hardware_id]) {
        map.setView([criticalBin.latitude, criticalBin.longitude], 16);
        binMarkers[criticalBin.hardware_id].openPopup();
        showToast(`⚠️ <strong>Simulated Incident:</strong> ${criticalBin.temperature}°C / ${criticalBin.methane} ppm breached at ${criticalBin.hardware_id} — webhooks dispatched.`);
    } else {
        showToast("No critical bin to simulate — seed demo data first.");
    }
}

// Fleet map helpers (unchanged behavior)
const sectorColors = {'CV-01':'#3498DB','CV-02':'#9B59B6','CV-03':'#E67E22','CV-04':'#1ABC9C','CV-05':'#E74C3C'};
const sectorPolygons = {
    'CV-01':[[18.0530,83.4020],[18.0530,83.4080],[18.0590,83.4080],[18.0590,83.4020]],
    'CV-02':[[18.0650,83.4060],[18.0650,83.4120],[18.0710,83.4120],[18.0710,83.4060]],
    'CV-03':[[18.0680,83.4120],[18.0680,83.4190],[18.0740,83.4190],[18.0740,83.4120]],
    'CV-04':[[18.0620,83.3970],[18.0620,83.4030],[18.0680,83.4030],[18.0680,83.3970]],
    'CV-05':[[18.0720,83.4160],[18.0720,83.4240],[18.0790,83.4240],[18.0790,83.4160]]
};

function initFleetMap(){
    if(fleetMap) return;
    fleetMap = L.map('fleetMap').setView([18.0675, 83.4094], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(fleetMap);
    Object.entries(sectorPolygons).forEach(([vid, coords]) => {
        L.polygon(coords, {color: sectorColors[vid]||'#666', fillOpacity:0.1, weight:2, dashArray:'6,4'})
         .addTo(fleetMap).bindPopup(`<b>Sector: ${vid}</b>`);
    });
}

async function loadFleetLocations(){
    if(!leafletLoaded) await ensureLeafletAndSocket();
    initFleetMap();
    fleetMarkers.forEach(m => fleetMap.removeLayer(m));
    fleetMarkers = [];
    try {
        const res = await fetch('/api/fleet-location');
        if(!res.ok){ console.warn('Fleet API not available'); return; }
        const fleet = await res.json();
        const listDiv = document.getElementById('fleetStatusList');
        listDiv.innerHTML = '';
        fleet.forEach(truck => {
            const color = truck.in_bounds ? '#27AE60' : '#E67E22';
            const icon = L.divIcon({ className:'', html: `<div style="background:${color};width:20px;height:20px;border-radius:50%;border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center;font-size:10px;">🚛</div>`, iconSize:[20,20] });
            const m = L.marker([truck.lat, truck.lon], {icon})
                .bindPopup(`<b>${truck.vehicle_id}</b><br>Driver: ${truck.worker_username}<br>Status: <b style="color:${color}">${truck.in_bounds?'In Bounds':'⚠️ Out of Bounds'}</b>`)
                .addTo(fleetMap);
            fleetMarkers.push(m);
            listDiv.innerHTML += `<div class="col-6 col-md-4 col-lg-3">
                <div class="rounded-3 p-3 border text-center" style="background:${truck.in_bounds?'#e8f8f5':'#fdf2e9'}; border-color:${color}!important;">
                    <div style="font-size:1.5rem;">🚛</div>
                    <div class="fw-bold small">${truck.vehicle_id}</div>
                    <div class="small" style="color:${color};">${truck.in_bounds?'✅ In Sector':'⚠️ Out of Bounds'}</div>
                </div>
            </div>`;
        });
        if(fleet.length===0) listDiv.innerHTML='<div class="col-12 text-muted text-center py-2">No active trucks found. Set workers to Active status.</div>';
    } catch(e){ console.error('Fleet load error:', e); }
}

// battery bars
document.querySelectorAll('[data-batt-width]').forEach(bar => { bar.style.width = bar.getAttribute('data-batt-width') + '%'; });

// Webhook & simulator functions (unchanged)
function setResponse(txt){ document.getElementById('responseBox').textContent = txt; }

function sendWhatsApp(){
    const fd = new FormData();
    fd.append('From', document.getElementById('wa_from').value);
    fd.append('Body', document.getElementById('wa_body').value);
    fd.append('NumMedia', document.getElementById('wa_num').value);
    fd.append('Latitude', document.getElementById('wa_lat').value);
    fd.append('Longitude', document.getElementById('wa_lon').value);
    const media = document.getElementById('wa_media').value.trim();
    if (media) fd.append('MediaUrl0', media);
    setResponse('POST /webhook/whatsapp …');
    fetch('/webhook/whatsapp', {method:'POST', body: fd})
        .then(r => r.text())
        .then(t => { setResponse(t); loadReports(); })
        .catch(e => setResponse('ERROR: ' + e));
}

function sendTelegram(){
    const payload = { message: { chat: { id: document.getElementById('tg_chat').value }, caption: document.getElementById('tg_caption').value, location: { latitude: parseFloat(document.getElementById('tg_lat').value), longitude: parseFloat(document.getElementById('tg_lon').value) } } };
    const file = document.getElementById('tg_file').value.trim(); if (file) payload.message.photo = [{ file_id: file }];
    setResponse('POST /webhook/telegram …');
    fetch('/webhook/telegram', { method:'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) })
        .then(r => r.json())
        .then(d => { setResponse(JSON.stringify(d, null, 2)); loadReports(); })
        .catch(e => setResponse('ERROR: ' + e));
}

function loadReports(){
    fetch('/api/illegal-reports?limit=10')
        .then(r => r.json())
        .then(rows => {
            const tb = document.getElementById('reportsBody');
            if (!rows.length){ tb.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No reports yet.</td></tr>'; return; }
            tb.innerHTML = rows.map(r => `
                <tr>
                    <td><strong>#${r.id}</strong></td>
                    <td>${r.category}</td>
                    <td><span class="badge ${r.status==='Pending'?'bg-warning text-dark':'bg-success'}">${r.status}</span></td>
                    <td class="small text-muted">${r.description || '—'}</td>
                    <td class="small">${r.latitude ?? '—'}</td>
                    <td class="small">${r.longitude ?? '—'}</td>
                    <td class="small text-muted">${r.timestamp ? r.timestamp.replace('T',' ').slice(0,19) : '—'}</td>
                </tr>`).join('');
        })
        .catch(e => console.error(e));
}

document.addEventListener('DOMContentLoaded', loadReports);

// ---- Job Queue Health (duration / retries / dead-letter KPIs) ----
function renderQueueHealth(data) {
    const kpisEl = document.getElementById('queueHealthKpis');
    if (kpisEl && data.kpis) {
        const k = data.kpis;
        const dlPct = Number(k.dead_letter_rate || 0);
        const dlClass = dlPct > 5 ? 'text-danger' : '';
        kpisEl.innerHTML = `
            <div class="col-md-3 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">Jobs Run</div>
                    <div class="fs-4 fw-bold">${k.jobs_run ?? 0}</div>
                </div>
            </div>
            <div class="col-md-3 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">🔄 Retries</div>
                    <div class="fs-4 fw-bold">${k.retries ?? 0}</div>
                </div>
            </div>
            <div class="col-md-3 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">💀 Dead-lettered</div>
                    <div class="fs-4 fw-bold ${dlClass}">${k.dead_lettered ?? 0}</div>
                </div>
            </div>
            <div class="col-md-3 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">⏱️ Avg Duration</div>
                    <div class="fs-4 fw-bold">${(k.avg_duration_s ?? 0).toFixed(2)}s</div>
                </div>
            </div>`;
    }
    const body = document.getElementById('queueHealthBody');
    if (!body) return;
    const rows = (data.kpis && data.kpis.per_function) || [];
    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">' +
            'No job runs recorded yet — trigger a dunning run or SMS to see instrumentation.</td></tr>';
        return;
    }
    body.innerHTML = rows.map(f => {
        const dlPct = Number(f.dead_letter_rate || 0);
        const dlClass = dlPct > 5 ? 'text-danger' : '';
        return `<tr>
            <td><code>${escapeHtml(f.func)}</code></td>
            <td>${f.runs}</td>
            <td class="${f.failed > 0 ? 'text-danger' : ''}">${f.failed}</td>
            <td>${f.retries}</td>
            <td class="${f.dead_lettered > 0 ? 'text-danger' : ''}">${f.dead_lettered}</td>
            <td class="small text-muted">${Number(f.avg_duration_s || 0).toFixed(2)}s</td>
            <td class="small ${dlClass}">${dlPct.toFixed(2)}%</td>
        </tr>`;
    }).join('');
}

async function loadQueueHealth() {
    try {
        const res = await fetch('/api/jobs/status');
        if (!res.ok) return;
        renderQueueHealth(await res.json());
    } catch (e) {
        console.warn('queue health load failed', e);
    }
}

// ---- Sensor-health control room (faulted bins + open incidents) ----
function statusBadge(status) {
    const cls = status === 'Critical' ? 'bg-danger'
        : status === 'Warning' ? 'bg-warning text-dark' : 'bg-success';
    return `<span class="badge ${cls}">${escapeHtml(status || 'Unknown')}</span>`;
}

function renderSensorFaults(data) {
    const k = data.kpis || {};
    const kpisEl = document.getElementById('sensorKpis');
    if (kpisEl) {
        const incClass = (k.open_incidents || 0) > 0 ? 'text-danger' : '';
        const maintClass = (k.maintenance_scheduled || 0) > 0 ? 'text-warning' : '';
        const woClass = (k.active_work_orders || 0) > 0 ? 'text-warning' : '';
        kpisEl.innerHTML = `
            <div class="col-md-3 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">🛠️ Faulted Bins</div>
                    <div class="fs-4 fw-bold ${(k.faulted_bins || 0) > 0 ? 'text-warning' : ''}">${k.faulted_bins ?? 0}</div>
                </div>
            </div>
            <div class="col-md-3 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">🚨 Open Sensor Incidents</div>
                    <div class="fs-4 fw-bold ${incClass}">${k.open_incidents ?? 0}</div>
                </div>
            </div>
            <div class="col-md-3 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">🧰 Maintenance Scheduled</div>
                    <div class="fs-4 fw-bold ${maintClass}">${k.maintenance_scheduled ?? 0}</div>
                </div>
            </div>
            <div class="col-md-3 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">📋 Active Work Orders</div>
                    <div class="fs-4 fw-bold ${woClass}">${k.active_work_orders ?? 0}</div>
                </div>
            </div>`;
    }
    const faultNav = document.getElementById('sensorFaultNavCount');
    if (faultNav) {
        faultNav.textContent = k.faulted_bins ?? 0;
        faultNav.classList.toggle('d-none', !(k.faulted_bins > 0));
    }

    const body = document.getElementById('sensorFaultBody');
    if (body) {
        const bins = data.bins || [];
        if (!bins.length) {
            body.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">✓ All bins healthy — no sensor faults.</td></tr>';
        } else {
            body.innerHTML = bins.map(b => `
                <tr>
                    <td><code>${escapeHtml(b.hardware_id)}</code>${b.open_incidents ? ' <span class="badge bg-danger" title="Open incident">!</span>' : ''}</td>
                    <td class="small">${escapeHtml(b.ward || '-')}</td>
                    <td>${b.level ?? '-'}%</td>
                    <td>${statusBadge(b.status)}</td>
                    <td class="small text-muted">${escapeHtml(b.fault_reason || '-')}</td>
                    <td class="small text-muted">${escapeHtml(b.last_ping ? b.last_ping.replace('T', ' ').slice(0, 16) : '-')}</td>
                    <td class="text-end">
                        <button class="btn btn-sm btn-outline-warning rounded-pill" data-clear-fault data-hw-id="${escapeHtml(b.hardware_id)}" data-label="🧹 Clear Fault">🧹 ${'Clear Fault'}</button>
                    </td>
                </tr>`).join('');
        }
    }

    const incBody = document.getElementById('sensorIncidentBody');
    if (incBody) {
        const incs = data.incidents || [];
        if (!incs.length) {
            incBody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">No open sensor-fault incidents.</td></tr>';
        } else {
            incBody.innerHTML = incs.map(inc => `
                <tr>
                    <td class="small">#${inc.id}</td>
                    <td><code>${escapeHtml(inc.hardware_id || 'bin#' + inc.bin_id)}</code></td>
                    <td><span class="badge bg-warning text-dark">${escapeHtml(inc.severity)}</span></td>
                    <td class="small text-muted">${escapeHtml(inc.description || '-')}</td>
                    <td class="small text-muted">${escapeHtml(inc.since ? inc.since.replace('T', ' ').slice(0, 16) : '-')}</td>
                    <td class="text-end">
                        ${inc.hardware_id
                            ? `<button class="btn btn-sm btn-outline-success rounded-pill" data-clear-fault data-hw-id="${escapeHtml(inc.hardware_id)}" data-label="✔ Resolve">✔ ${'Resolve'}</button>`
                            : '<span class="text-muted small">—</span>'}
                    </td>
                </tr>`).join('');
        }
    }
}

async function loadSensorFaults() {
    try {
        const res = await fetch('/api/sensor-faults');
        if (!res.ok) return;
        renderSensorFaults(await res.json());
    } catch (e) {
        console.warn('sensor health load failed', e);
    }
}

// ── Maintenance work orders (fault cleared with a scheduled follow-up) ──
// The worker pool is cached from /api/maintenance so the schedule form's
// dropdown works even if the modal is opened before the table finishes loading.
let maintenanceWorkers = [];

function renderMaintenance(data) {
    const body = document.getElementById('maintenanceBody');
    if (!body) return;
    const orders = data.orders || [];
    if (!orders.length) {
        body.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-4">✓ No maintenance work orders — cleared faults are either back in service or tracked here once scheduled.</td></tr>';
        return;
    }
    body.innerHTML = orders.map(o => {
        const dueTxt = o.due_date ? o.due_date.replace('T', ' ').slice(0, 10) : '—';
        const overdueBadge = o.overdue ? ' <span class="badge bg-danger" title="Overdue">Overdue</span>' : '';
        let statusBadge = '<span class="badge bg-warning text-dark">Scheduled</span>';
        if (o.status === 'In Progress') statusBadge = '<span class="badge bg-primary">In Progress</span>';
        else if (o.status === 'Completed') statusBadge = '<span class="badge bg-success">✔ Completed</span>';
        const workerTxt = o.worker_name
            ? `${escapeHtml(o.worker_name)}${o.vehicle_id ? ' <span class="text-muted">(' + escapeHtml(o.vehicle_id) + ')</span>' : ''}`
            : '<span class="text-muted">Unassigned</span>';
        const action = o.status === 'Completed'
            ? '<span class="text-muted small">—</span>'
            : `<button class="btn btn-sm btn-outline-success rounded-pill" data-maint-complete data-maint-id="${o.id}">✔ Mark Done</button>`;
        return `<tr>
            <td class="small">#${o.id}</td>
            <td><code>${escapeHtml(o.hardware_id || 'bin#' + o.bin_id)}</code></td>
            <td class="small">${escapeHtml(o.ward || '-')}</td>
            <td class="small">${workerTxt}</td>
            <td class="small text-nowrap">${dueTxt}${overdueBadge}</td>
            <td>${statusBadge}</td>
            <td class="small text-muted">${escapeHtml(o.notes || '-')}</td>
            <td class="text-end">${action}</td>
        </tr>`;
    }).join('');
}

async function loadMaintenance() {
    try {
        const res = await fetch('/api/maintenance');
        if (!res.ok) return;
        const data = await res.json();
        maintenanceWorkers = data.workers || [];
        renderMaintenance(data);
    } catch (e) {
        console.warn('maintenance load failed', e);
    }
}

// ── Clear-fault modal (with optional maintenance scheduling) ──
let cfTargetHw = null;

function toggleCfMaintFields() {
    const show = document.getElementById('cfModeMaint')?.checked;
    const fields = document.getElementById('cfMaintFields');
    if (fields) fields.classList.toggle('d-none', !show);
}

function populateCfWorkers() {
    const sel = document.getElementById('cfWorker');
    if (!sel) return;
    sel.innerHTML = '<option value="">Select worker…</option>' + maintenanceWorkers.map(w =>
        `<option value="${w.id}">${escapeHtml(w.name)}${w.vehicle_id ? ' (' + escapeHtml(w.vehicle_id) + ')' : ''}</option>`
    ).join('');
}

async function openClearFaultModal(hwId) {
    if (!hwId) return;
    cfTargetHw = hwId;
    document.getElementById('cfHwId').textContent = hwId;
    const d = new Date(Date.now() + 3 * 86400000);
    const due = document.getElementById('cfDueDate');
    if (due) due.value = d.toISOString().slice(0, 10);
    document.getElementById('cfModeClear').checked = true;
    document.getElementById('cfNotes').value = '';
    toggleCfMaintFields();
    if (maintenanceWorkers.length === 0) await loadMaintenance();
    populateCfWorkers();
    const m = document.getElementById('clearFaultModal');
    if (m) bootstrap.Modal.getOrCreateInstance(m).show();
}

async function submitClearFault() {
    const btn = document.getElementById('cfSubmitBtn');
    if (!cfTargetHw || !btn) return;
    const schedule = document.getElementById('cfModeMaint')?.checked === true;
    const payload = { schedule_maintenance: schedule };
    if (schedule) {
        const workerId = document.getElementById('cfWorker')?.value;
        const dueDate = document.getElementById('cfDueDate')?.value;
        if (!workerId) { showToast('⚠️ Select a maintenance worker to schedule follow-up.'); return; }
        if (!dueDate) { showToast('⚠️ Pick a due date for the work order.'); return; }
        payload.worker_id = Number(workerId);
        payload.due_date = dueDate;
        payload.notes = (document.getElementById('cfNotes')?.value || '').trim();
    }
    btn.disabled = true; btn.textContent = '…';
    try {
        const res = await fetch('/api/bins/' + encodeURIComponent(cfTargetHw) + '/clear-fault', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.message || 'clear failed');
        const msg = data.maintenance_scheduled
            ? `🧰 <strong>Fault cleared:</strong> ${escapeHtml(cfTargetHw)} — work order #${data.maintenance_order_id} scheduled.`
            : `🧹 <strong>Fault cleared:</strong> ${escapeHtml(cfTargetHw)} restored — ${data.resolved_incidents ?? 0} incident(s) resolved.`;
        showToast(msg);
        const m = document.getElementById('clearFaultModal');
        if (m) bootstrap.Modal.getInstance(m)?.hide();
        cfTargetHw = null;
        loadSensorFaults();
        loadMaintenance();
    } catch (e) {
        showToast(`⚠️ Could not clear fault on ${escapeHtml(cfTargetHw)}: ${escapeHtml(e.message)}`);
    } finally {
        btn.disabled = false; btn.textContent = '✔ Confirm Clear';
    }
}

async function completeMaintenance(orderId, btn) {
    if (!orderId) return;
    if (!confirm('Mark this maintenance work order as done? The bin returns to service and the action is audited.')) return;
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
        const res = await fetch('/api/maintenance/' + encodeURIComponent(orderId) + '/complete', {
            method: 'POST',
            headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.message || 'complete failed');
        showToast('✔ Maintenance work order #' + orderId + ' completed.');
        loadMaintenance();
        loadSensorFaults();
    } catch (e) {
        showToast('⚠️ Could not complete work order: ' + escapeHtml(e.message));
        if (btn) { btn.disabled = false; btn.textContent = '✔ Mark Done'; }
    }
}

// Delegated clicks: buttons are re-rendered on every refresh, and values flow
// through data-* attributes (never inline onclick strings) so DB-controlled
// values can never break out into executable JS.
document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('click', (e) => {
        const clearBtn = e.target.closest('[data-clear-fault]');
        if (clearBtn && clearBtn.dataset.hwId) { openClearFaultModal(clearBtn.dataset.hwId); return; }
        const doneBtn = e.target.closest('[data-maint-complete]');
        if (doneBtn && doneBtn.dataset.maintId) completeMaintenance(doneBtn.dataset.maintId, doneBtn);
    });
});

// ---- Live updates via Socket.IO (deferred until socket loaded) ----
function connectLive() {
    if (typeof io === 'undefined') { console.warn('socket.io client not loaded'); return; }
    const socket = io({ transports: ['websocket', 'polling'] });
    const liveDot = document.getElementById('liveIndicator');
    socket.on('connect', () => { if (liveDot) { liveDot.className = 'badge bg-success'; liveDot.textContent = 'LIVE'; } });
    socket.on('disconnect', () => { if (liveDot) { liveDot.className = 'badge bg-secondary'; liveDot.textContent = 'OFFLINE'; } });
    socket.on('connect_error', () => { if (liveDot) { liveDot.className = 'badge bg-warning text-dark'; liveDot.textContent = 'RECONNECT'; } });

    socket.on('bin_update', (data) => {
        const bin = smartBins.find(b => b.hardware_id === data.hardware_id);
        if (bin) Object.assign(bin, data);
        const marker = binMarkers[data.hardware_id];
        if (marker) updateBinMarker(bin || data);
    });

    socket.on('maintenance_update', () => {
        // A worker started/completed a work order (or a bin clear auto-closed
        // one) — refresh the control room so overdue/status badges stay live.
        loadMaintenance();
        loadSensorFaults();
    });

    socket.on('fleet_update', (payload) => {
        if (payload && payload.fleet) { if (typeof fleetMap !== 'undefined' && fleetMap) loadFleetLocations(); }
    });

    socket.on('dispatch_nudge', (data) => {
        // A bin just crossed the 6h overflow threshold — refresh the queue
        // and surface a toast so the control room can nudge drivers.
        refreshDispatchQueue();
        if (data && data.hardware_id) {
            showToast(`🚨 <strong>${data.hardware_id}</strong> forecast to overflow in ~${data.overflow_eta_hours}h — workers nudged.`);
        }
    });

    socket.on('dispatch_update', () => refreshDispatchQueue());
}

// ---- Proactive dispatch queue (admin control room) ----
function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
}

function renderDispatchQueue(bins) {
    const body = document.getElementById('dispatchQueueBody');
    const kpis = document.getElementById('dispatchKpis');
    const navCount = document.getElementById('dispatchNavCount');
    if (!body) return;

    if (navCount) navCount.textContent = bins.length;
    if (kpis) {
        const urgent = bins.filter(b => b.urgent).length;
        const pending = bins.filter(b => b.dispatch_status === 'pending' || b.dispatch_status === 'available').length;
        const assigned = bins.filter(b => b.dispatch_status === 'assigned').length;
        kpis.innerHTML = `
            <div class="col-md-4 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">Forecast Bins</div>
                    <div class="fs-4 fw-bold">${bins.length}</div>
                </div>
            </div>
            <div class="col-md-4 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">⚠️ Urgent (&lt;24h)</div>
                    <div class="fs-4 fw-bold text-danger">${urgent}</div>
                </div>
            </div>
            <div class="col-md-4 col-sm-6">
                <div class="border rounded-3 p-3 text-center h-100">
                    <div class="text-muted small fw-bold">🚛 Assigned</div>
                    <div class="fs-4 fw-bold text-success">${assigned} / ${bins.length}</div>
                </div>
            </div>`;
    }

    if (!bins.length) {
        body.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-4">✅ No bins in the proactive queue right now.</td></tr>';
        return;
    }
    body.innerHTML = bins.map(b => {
        const eta = (b.overflow_eta_hours !== null && b.overflow_eta_hours !== undefined)
            ? b.overflow_eta_hours + ' h' : '—';
        let badge;
        if (b.dispatch_status === 'assigned') badge = '<span class="badge bg-success">Assigned</span>';
        else if (b.dispatch_status === 'pending') badge = '<span class="badge bg-warning text-dark">Queued</span>';
        else badge = '<span class="badge bg-secondary">Available</span>';
        const workerTxt = b.mine ? 'You' : (b.assigned_worker_id ? '#' + b.assigned_worker_id : '—');
        return `<tr>
            <td><strong>${escapeHtml(b.hardware_id)}</strong></td>
            <td class="small">${escapeHtml(b.ward)}</td>
            <td><span class="badge ${b.level >= 80 ? 'bg-danger' : 'bg-light text-dark'}">${b.level}%</span></td>
            <td>${b.urgent ? '<span class="text-danger fw-bold">⏱ ' + eta + '</span>' : eta}</td>
            <td>${badge}</td>
            <td class="small">${workerTxt}</td>
        </tr>`;
    }).join('');
}

async function refreshDispatchQueue() {
    try {
        const res = await fetch('/api/dispatch/queue');
        if (!res.ok) return;
        const data = await res.json();
        renderDispatchQueue(data.bins || []);
    } catch (e) {
        console.warn('dispatch queue refresh failed', e);
    }
}


// Refetch bin telemetry and rebuild markers (GIS "Refresh Telemetry" button).
async function refreshBinMarkers() {
    try {
        const res = await fetch('/api/bins');
        if (!res.ok) { showToast('⚠️ Could not refresh telemetry.'); return; }
        smartBins = await res.json();
        if (map && smartBins.length) buildBinMarkers();
        showToast('✅ Telemetry refreshed — ' + smartBins.length + ' bins.');
    } catch (e) {
        console.error('Telemetry refresh failed:', e);
        showToast('⚠️ Telemetry refresh failed.');
    }
}

// Mobile section jumper: in-page sections use setActive(), external pages navigate.
function adminMobileJump(selectEl) {
    const v = selectEl.value;
    if (!v) return;
    if (v.startsWith('/')) {
        window.location.href = v;
        return;
    }
    if (typeof setActive === 'function') setActive(v);
}

// Auto-initialize maps when GIS map enters viewport (fallback for deep links)
const gisObserver = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { initMaps(); gisObserver.disconnect(); } });
}, { rootMargin: '0px', threshold: 0.1 });
const gisEl = document.getElementById('gisMap'); if (gisEl) gisObserver.observe(gisEl);

// Auto-load fleet map if visible
const fleetObserver = new IntersectionObserver((entries) => {
    entries.forEach(e => { if(e.isIntersecting) { initFleetMap(); fleetObserver.disconnect(); } });
});
const fleetEl = document.getElementById('fleetMap'); if(fleetEl) fleetObserver.observe(fleetEl);

// Expose some functions globally for inline button onclick handlers
window.simulateAnomalyTrigger = simulateAnomalyTrigger;
window.executeRoutingDispatch = executeRoutingDispatch;
window.loadFleetLocations = loadFleetLocations;
window.loadSensorFaults = loadSensorFaults;
window.loadMaintenance = loadMaintenance;
window.sendWhatsApp = sendWhatsApp;
window.sendTelegram = sendTelegram;
window.toggleCompactor = toggleCompactor;
window.refreshBinMarkers = refreshBinMarkers;
window.refreshDispatchQueue = refreshDispatchQueue;
window.adminMobileJump = adminMobileJump;
window.loadQueueHealth = loadQueueHealth;

// Auto-load the dispatch queue when the control room opens.
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('dispatchQueueBody')) refreshDispatchQueue();
});

// Auto-load queue-health KPIs when the control room opens.
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('queueHealthKpis')) loadQueueHealth();
});

// ---- Admin notification bell (dead-letter alerts + status pushes) ----
let adminNotifRefreshTimer = null;

function toggleAdminNotifications() {
    const panel = document.getElementById('adminNotifPanel');
    if (!panel) return;
    const showing = !panel.classList.contains('d-none');
    panel.classList.toggle('d-none', showing);
    if (!showing) loadAdminNotifications();
}

async function loadAdminNotifications() {
    try {
        const res = await fetch('/api/notifications');
        if (!res.ok) return;
        const notes = await res.json();
        const list = document.getElementById('adminNotifList');
        const badge = document.getElementById('adminNotifBadge');
        if (!list) return;
        const unread = notes.filter(n => !n.read).length;
        if (badge) {
            badge.textContent = unread;
            badge.classList.toggle('d-none', unread === 0);
        }
        if (!notes.length) {
            list.innerHTML = '<div class="text-center text-muted small py-3">No notifications yet.</div>';
            return;
        }
        list.innerHTML = notes.map(n => `
            <a href="${escapeHtml(n.link || '/admin')}" class="d-block text-decoration-none text-dark rounded-3 px-2 py-2 mb-1 ${n.read ? '' : 'bg-light'}" style="${n.read ? 'opacity:0.7;' : ''}">
                <div class="small">${escapeHtml(n.message)}</div>
                <div class="text-muted" style="font-size:0.7rem;">${n.created_at ? escapeHtml(String(n.created_at).replace('T', ' ').slice(0, 19)) : ''}</div>
            </a>`).join('');
    } catch (e) {
        console.warn('admin notifications load failed', e);
    }
}

async function markAdminNotificationsRead() {
    try {
        await fetch('/api/notifications/mark-read', {
            method: 'POST',
            headers: { 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content }
        });
        const badge = document.getElementById('adminNotifBadge');
        if (badge) badge.classList.add('d-none');
        loadAdminNotifications();
    } catch (e) {
        console.warn('mark admin notifications read failed', e);
    }
}

// Live admin alerts: one SSE stream pushes fault events the instant they're
// written (Redis pub/sub; the stream's 5s DB-poll fallback covers no-Redis).
// The first burst on connect is the unread snapshot — refresh the bell but
// don't toast history; only toast pushes that arrive after the snapshot.
function connectAdminNotifStream() {
    if (typeof EventSource === 'undefined' || !document.getElementById('adminNotifBadge')) return;
    const es = new EventSource('/api/notifications/stream');
    let openedAt = 0;
    // onopen fires on EVERY (re)connect — reset the snapshot window so a
    // reconnect re-sends the unread batch without re-toasting it as live.
    es.onopen = () => { openedAt = Date.now(); };
    es.onmessage = (e) => {
        if (!e.data) return;
        loadAdminNotifications();
        // Messages can carry device-controlled text (hardware ids) — escape
        // before showToast's innerHTML render.
        if (Date.now() - openedAt > 1500) showToast('🔔 ' + escapeHtml(e.data));
    };
    es.onerror = () => { /* browser auto-reconnects */ };
}

// Refresh the bell periodically so dead-letter alerts surface without a reload.
if (document.getElementById('adminNotifBadge')) {
    loadAdminNotifications();
    adminNotifRefreshTimer = setInterval(loadAdminNotifications, 30000);
    connectAdminNotifStream();
}

window.toggleAdminNotifications = toggleAdminNotifications;
window.markAdminNotificationsRead = markAdminNotificationsRead;
