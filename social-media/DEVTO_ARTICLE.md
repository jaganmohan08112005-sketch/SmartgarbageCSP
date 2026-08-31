# Dev.to Article — Copy-Paste Ready

**Go to https://dev.to → Create Post → Paste everything below**

---

## Title:
```
How I Built an Open-Source Waste Management Portal for an Indian Municipality
```

## Tags:
```
python, flask, opensource, civictech, waste-management
```

## Body:

```markdown
## The Problem

Waste management in rural India is challenging. Citizens don't know collection schedules, can't report missed pickups, and have no visibility into how their taxes are being used.

## The Solution

I built **SmartGarbage** — an open-source portal that lets citizens:

- Check collection schedules for their ward
- Report missed pickups with GPS + photos
- View live transparency dashboards
- Earn Green Points for waste segregation

## Tech Stack

- **Backend:** Python/Flask
- **Database:** PostgreSQL (Supabase)
- **Frontend:** Bootstrap 5, Leaflet.js, Chart.js
- **Deployment:** Docker on Render
- **ML:** scikit-learn for overflow prediction

## Key Features

### 1. GPS Photo Verification

When a citizen reports a missed pickup, the app extracts EXIF GPS data from the photo and cross-checks it against the submitted device location. This prevents fake reports from internet photos.

```python
def _photo_gps_from_upload(file_storage):
    """Extract EXIF GPS from uploaded photo."""
    from PIL import Image
    import io
    file_storage.seek(0)
    buf = io.BytesIO(file_storage.read())
    img = Image.open(buf)
    gps = _extract_gps_from_exif(img)
    img.close()
    file_storage.seek(0)
    return gps
```

### 2. Service Worker for Offline Support

The app uses a service worker with 3-tier caching:

- **Static assets:** cache-first (never revalidates)
- **HTML pages:** stale-while-revalidate (instant repeat visits)
- **CDN resources:** stale-while-revalidate (longer TTL)

```javascript
// Stale-while-revalidate for HTML pages
async function staleWhileRevalidatePages(req) {
    const cached = await caches.match(req);
    const fetchPromise = fetch(req).then(res => {
        if (res.ok && res.status === 200 && !res.redirected) {
            const cache = caches.open(PAGES_CACHE);
            cache.then(c => c.put(req, res.clone()));
        }
        return res;
    }).catch(() => cached);
    return cached || fetchPromise;
}
```

### 3. Bilingual Interface

Supports English and Telugu using Flask-Babel. Citizens can switch languages with one click.

### 4. Dark Mode + Font Scaling

Accessibility features that most government sites don't have:

- Dark mode toggle
- A- A A+ font scaling
- High contrast mode
- WCAG 2.1 AA compliant mega menu

### 5. ML Predictions

Uses scikit-learn to predict when bins will overflow, enabling proactive dispatch.

## Open Source

The code is on GitHub under MIT license. Looking for contributors!

**GitHub:** [SmartGarbage](https://github.com/jaganmohan08112005-sketch/SmartgarbageCSP)
**Live:** [smartgarbage.eu.org](https://smartgarbage.eu.org)

## What I Learned

1. **Flask is powerful** — it handled everything from auth to IoT webhooks
2. **Service workers are magic** — instant repeat visits, offline support
3. **Accessibility matters** — WCAG compliance makes the app usable for everyone
4. **Open source builds trust** — the community helps you improve

## Next Steps

- Add more language support (Hindi, Tamil)
- Integrate with more IoT sensors
- Build a mobile app wrapper
- Get government recognition

---

*This is my first open-source project. Feedback welcome!*
```

---

## Publishing Checklist

- [ ] Title is compelling (under 100 characters)
- [ ] Tags are relevant: python, flask, opensource, civictech
- [ ] Code snippets are formatted correctly
- [ ] Links work (GitHub, live site)
- [ ] Cover image added (optional but recommended)
- [ ] Published on Tuesday-Thursday for maximum visibility
