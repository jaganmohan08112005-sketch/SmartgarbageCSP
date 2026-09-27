---
name: agents-skills-smart-garbage-video-generator-skill-md
description: agents-skills-smart-garbage-video-generator-skill-md skill
---

name: smart-garbage-video-generator
description: Generates a complete video production blueprint—including a multi-part narrative script, visual storyboard, and live deployment demonstration guide—tailored for a Smart Garbage Management System community service project.
---

# Smart Garbage Management System Video Generator

## Goal
To convert the hardware layout, cloud architecture, and dashboard interfaces of the Smart Garbage Management System into a compelling demo video script and storyboard. This skill balances highlighting real-world community impact (sanitation, health, municipal efficiency) with a clear technical deployment walkthrough.

## Workflow

### 1. Ingest Project Context
* Scan the repository for IoT components (e.g., ESP32, Arduino, Ultrasonic sensors), web frameworks (e.g., React, Node.js, Python), and cloud databases.
* Map out the data flow from physical trash bin sensors to the cloud backend and the final municipal monitoring dashboard.

### 2. Narrative Script & Storyboard Design
Generate a synchronized markdown matrix linking voiceover lines to visual scenes across five key video milestones:
* **The Community Problem (0:00 - 0:25):** Establish the visual impact of overflowing public trash bins and civic sanitation challenges.
* **The IoT IoT System Overview (0:25 - 0:55):** Diagram the structural connection between smart bins, wireless networks, and the central server.
* **Dashboard Features & Demo (0:55 - 1:45):** Highlight live data updates, threshold alerts (e.g., bin over 80% capacity), and optimized collection routing map UIs.
* **Step-by-Step Deployment (1:45 - 2:45):** Walk through flash commands for microcontrollers, backend server initializations (`npm start` or docker triggers), and successful data handshakes.
* **Civic Call to Action (2:45 - End):** Highlight long-term environmental metrics, resource savings, and links to the open-source repository.

### 3. Pacing & Asset Integration
* Enforce clear narrative markers like `[PAUSE]` within the script to align cleanly with human voiceovers or text-to-speech tools.
* Define strict visual asset guidelines specifying whether a scene requires `[Hardware B-Roll]`, `[UI Software Demo]`, or `[Terminal Log Capture]`.

## Constraints & Rules
* **Civic-Technical Balance:** The output must not skew entirely technical. It must frame database updates and sensor feeds around solving the core human problem: keeping streets clean.
* **Legible Code Snippets:** When presenting code, only display critical configurations (WiFi credentials setup, distance threshold triggers, API endpoints). Avoid dense logic dumps.
* **Visual Scannability:** Keep the generated storyboard highly readable so a video editor or narrator can look at the matrix and instantly grasp the scene objective.
