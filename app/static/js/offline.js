/* ============================================================
   SmartGarbage — Offline Form Queue
   Queues form submissions in IndexedDB when offline,
   then replays them when connectivity is restored.
   ============================================================ */

const OFFLINE_DB_NAME = 'smartgarbage-offline';
const OFFLINE_DB_VERSION = 1;
const OFFLINE_STORE = 'pending-forms';

function openOfflineDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(OFFLINE_DB_NAME, OFFLINE_DB_VERSION);
        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(OFFLINE_STORE)) {
                db.createObjectStore(OFFLINE_STORE, { keyPath: 'id', autoIncrement: true });
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function queueFormSubmission(url, method, body, formData) {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_STORE);
    store.add({
        url,
        method,
        body,
        formData,
        timestamp: Date.now()
    });
    return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

async function getQueuedSubmissions() {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readonly');
    const store = tx.objectStore(OFFLINE_STORE);
    const request = store.getAll();
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function removeQueuedSubmission(id) {
    const db = await openOfflineDB();
    const tx = db.transaction(OFFLINE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_STORE);
    store.delete(id);
    return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve();
        tx.onerror = () => reject(tx.error);
    });
}

async function replayQueuedSubmissions() {
    const items = await getQueuedSubmissions();
    for (const item of items) {
        try {
            const response = await fetch(item.url, {
                method: item.method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(item.body)
            });
            if (response.ok) {
                await removeQueuedSubmission(item.id);
                console.log('Replayed queued submission:', item.url);
            }
        } catch (e) {
            console.warn('Failed to replay queued submission:', item.url, e);
        }
    }
}

function setupOfflineForms() {
    const forms = document.querySelectorAll('form[data-offline-queue]');
    forms.forEach(form => {
        form.addEventListener('submit', async (e) => {
            if (!navigator.onLine) {
                e.preventDefault();
                const url = form.action || window.location.href;
                const method = form.method || 'POST';
                const formData = new FormData(form);
                const body = {};
                formData.forEach((value, key) => { body[key] = value; });
                await queueFormSubmission(url, method, body, formData);
                showToast('📥 Form saved offline — will sync when you reconnect');
            }
        });
    });
}

window.addEventListener('online', () => {
    console.log('Back online — replaying queued submissions');
    replayQueuedSubmissions();
});

window.addEventListener('DOMContentLoaded', () => {
    setupOfflineForms();
});
