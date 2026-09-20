/**
 * main.js – Application initialization, state, utilities, and polling
 * 
 * This module handles:
 * - Server data initialization
 * - Client-side state management
 * - Auto-reload on version change
 * - Countdown and progress bar updates
 * - Dynamic HTML script activation
 * 
 * Event handlers for user interactions are in handlers.js
 */

// ============================================================
// INITIALIZATION: Load server data from hidden data element
// ============================================================
const serverDataEl = document.getElementById('server-data');
const SERVER_DATA = {
    version:          Number(serverDataEl.dataset.version),
    countdownSeconds: Number(serverDataEl.dataset.countdown)
};

// ============================================================
// STATE: Shared client-side state for selected target and view
// ============================================================

/** Currently selected row index in the table */
let currentIndex = 0;

/** Current map view mode: 'daily' or 'total' (cumulative) */
let currentMaptype = 'daily';

/** Group number (gn) of selected target (1-based)*/
let currentGn = '1';

/** Member number (mn) of selected target (0-based) */
let currentMn = '0';


// ============================================================
// UTILITY: Helpers for working with dynamic content
// ============================================================

/**
 * Execute <script> tags inside dynamically injected HTML.
 * 
 * When fetching HTML from the server and inserting it with innerHTML,
 * script tags don't execute automatically. This function finds all script
 * tags in a container and re-executes them so that Plotly.js and other
 * initialization code runs properly.
 * 
 * @param {HTMLElement} container - Element containing injected HTML
 */
function activateScripts(container) {
    container.querySelectorAll('script').forEach(oldScript => {
        const newScript = document.createElement('script');
        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
    });
}

/**
 * Update the heading for Figure 1 based on the current map type.
 * The heading changes to reflect whether showing daily or cumulative visits.
 */
function updateFig1Heading() {
    const headings = {
        daily: 'Daily visits',
        total: 'Cumulative visits to date'
    };
    document.getElementById('fig1-heading').textContent = headings[currentMaptype];
}


// ============================================================
// AUTO-RELOAD: Monitor server version and reload if changed
// ============================================================

const loadedVersion = SERVER_DATA.version;

/**
 * Check if server has a new version and reload if so.
 * 
 * This ensures users always have the latest UI code without manual refresh.
 * Polls every 2 seconds.
 */
setInterval(async () => {
    try {
        const resp = await fetch('/check_update');
        const data = await resp.json();
        if (data.version > loadedVersion) {
            location.reload();
        }
    } catch (error) {
        console.error('Error checking for updates:', error);
    }
}, 2000);


// ============================================================
// COUNTDOWN & PROGRESS BAR: Update UI with refresh timing
// ============================================================

/** Seconds remaining until next data update */
let remaining = SERVER_DATA.countdownSeconds;

/** Whether server is currently processing (updating data) */
let updating = false;

/** Progress percentage (0-1) for current update operation */
let progress = 0;

/** Status message to display during update (e.g., "Fetching data...") */
let progressMsg = '';

/**
 * Update countdown display and progress bar.
 * When updating == true, shows progress bar and status message.
 * When updating == false, shows seconds until next update (counts down).
 */
function updateCountdown() {
    const el = document.getElementById('countdown-value');
    const fill = document.getElementById('progress-fill');
    const track = document.querySelector('.progress-track');

    if (updating) {
        if (track) track.style.display = 'block';
        el.textContent = progressMsg || 'Processing...';
        if (fill) fill.style.width = Math.round(progress * 100) + '%';
    } else {
        if (track) track.style.display = 'none';
        if (remaining > 0) {
            el.textContent = 'Next simulated date in ' + Math.ceil(remaining) + 's';
            remaining -= 1;
        } else {
            el.textContent = 'Next simulated date in 0s';
        }
    }
}

/**
 * Fetch latest update status from server.
 * 
 * Updates the global state variables: updating, progress, progressMsg, remaining
 */
function refreshCountdown() {
    fetch('/next_update')
        .then(r => r.json())
        .then(data => {
            updating = data.updating;
            progress = data.progress || 0;
            progressMsg = data.progress_msg || '';
            if (!updating) {
                remaining = Math.max(0, data.next_update - data.server_time);
            }
        })
        .catch(err => console.error('Error refreshing countdown:', err));
}

// Initialize countdown on page load
updateCountdown();

// Update countdown and refresh server status every 1 second
setInterval(() => {
    updateCountdown();
    refreshCountdown();
}, 1000);