/* admin.js - extracted from admin.html
   Handles sidebar nav, map markers, fleet map, webhook simulators,
   and live socket connections. Also lazy-loads Leaflet and Socket.IO. */
"use strict";

// ---- Sidebar nav: scroll-to-section + active highlight on click ----
document.addEventListener('DOMContentLoaded', () => {
    const navLinks = document.querySelectorAll('#admin-pills a[data-section]');

    function setActive(sectionId) {
        navLinks.forEach(link => {
            if (link.dataset.section === sectionId) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.dataset.section;
            const targetEl = document.getElementById(targetId);
            if (targetEl) {
                const yOffset = -100;
                const y = targetEl.getBoundingClientRect().top + window.pageYOffset + yOffset;
                window.scrollTo({ top: y, behavior: 'smooth' });
            }
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

let leafletLoaded = false;
async function ensureLeafletAndSocket() {
    if (leafletLoaded) return;
    await loadScript(LEAFLET_JS);
    await loadScript(SOCKET_IO_JS);
    leafletLoaded = true;
}

// ---- Application state ----
let smartBins = [];
let currentBinHwId = null;
let map = null;
let binMarkers = {};
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
    smartBins.forEach(bin => {
        const marker = L.circleMarker([bin.latitude, bin.longitude], {
            radius: 8,
            fillColor: getMarkerColor(bin.status),
            color: '#FFFFFF',
            weight: 2,
            opacity: 1,
            fillOpacity: 0.9
        }).addTo(map);

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
        const res = await fetch('/admin/toggle-compactor/' + currentBinHwId, {method: 'POST'});
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

// Dijkstra route optimize caller
async function executeRoutingDispatch() {
    const response = await fetch('/api/route-optimize');
    if (!response.ok) return;
    const data = await response.json();
    if (data.route && data.route.length > 0) {
        if (currentRouteLine) { map.removeLayer(currentRouteLine); }
        const coords = data.route.map(node => [node.lat, node.lon]);
        currentRouteLine = L.polyline(coords, { color: '#2C3E50', weight: 5, opacity: 0.75, dashArray: '10, 10' }).addTo(map);
        map.fitBounds(currentRouteLine.getBounds());
        const infoBanner = document.getElementById('routingInfo');
        infoBanner.classList.remove('d-none');
        document.getElementById('routeCount').innerText = data.critical_count;
        document.getElementById('routeDistance').innerText = data.total_distance_km;
        const labels = data.route.map(node => node.label);
        document.getElementById('routePathText').innerHTML = `<b>Sequenced Pickups Route:</b> ${labels.join(' ➔ ')}` + (data.co2_saved_kg ? ` &nbsp;|&nbsp; 🌿 <b>${data.co2_saved_kg} kg CO₂ saved</b> vs fixed routes` : '');
        alert(`✅ Dijkstra Route Optimized!\nDistance: ${data.total_distance_km} km across ${data.critical_count} critical bins.\n🌿 Estimated CO₂ saved: ${data.co2_saved_kg || 0} kg vs traditional fixed routes.`);
    }
}

function simulateAnomalyTrigger() {
    const criticalBin = smartBins.find(b => b.hardware_id === "BIN-302");
    if (criticalBin && binMarkers[criticalBin.hardware_id]) {
        map.setView([criticalBin.latitude, criticalBin.longitude], 16);
        binMarkers[criticalBin.hardware_id].openPopup();
        alert("⚠️ Simulated Incident Triggered: High temperature (72.1°C) and hazardous methane levels (850 ppm) breached at BIN-302 inside RTC Colony! Webhooks dispatched to regional emergency response teams.");
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

    socket.on('fleet_update', (payload) => {
        if (payload && payload.fleet) { if (typeof fleetMap !== 'undefined' && fleetMap) loadFleetLocations(); }
    });
}

// Auto-initialize maps when GIS map enters viewport
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
window.sendWhatsApp = sendWhatsApp;
window.sendTelegram = sendTelegram;
window.toggleCompactor = toggleCompactor;
