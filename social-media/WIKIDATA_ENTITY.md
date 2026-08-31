# Wikidata Entity — Step-by-Step Guide

## Create Entity (10 minutes)

### Step 1: Go to Wikidata
```
https://www.wikidata.org
```

### Step 2: Click "Create a new item"
- Top right corner → "Create a new item"

### Step 3: Fill in Basic Info
```
Label: SmartGarbage Chintalavalasa
Description: Digital waste management portal in Andhra Pradesh, India
Language: English
```

### Step 4: Click "Create"

### Step 5: Add Properties (Click "Add statement" for each)

**Property 1:**
```
Property: instance of
Value: website
```

**Property 2:**
```
Property: inception
Value: 2026
```

**Property 3:**
```
Property: country
Value: India
```

**Property 4:**
```
Property: official website
Value: https://smartgarbage.eu.org
```

**Property 5:**
```
Property: programming language
Value: Python
```

**Property 6:**
```
Property: license
Value: MIT License
```

**Property 7:**
```
Property: owned by
Value: Chintalavalasa Gram Panchayat
```

**Property 8:**
```
Property: location
Value: Chintalavalasa, Vizianagaram District, Andhra Pradesh, India
```

**Property 9:**
```
Property: topic's main category
Value: Waste management in India
```

**Property 10:**
```
Property: developer
Value: Jagan Mohan
```

### Step 6: Click "Save" after each property

### Step 7: Verify
- Your entity URL will be: `https://www.wikidata.org/wiki/Q[number]`
- It may take 24-48 hours to appear in Google Knowledge Graph

---

## Alternative: Use Wikidata API (Advanced)

If you have a Wikidata account, you can create the entity via API:

```bash
# First, get a Wikidata account at https://www.wikidata.org/wiki/Special:CreateAccount

# Then use the API to create the entity
# See: https://www.wikidata.org/wiki/Wikidata:API

# Or use the QuickStatements tool:
# https://quickstatements.toolforge.org/
```

---

## Verify Entity Exists

After creating, verify at:
```
https://www.wikidata.org/wiki/Special:Search?search=SmartGarbage+Chintalavalasa
```

It should appear in search results within 24 hours.
