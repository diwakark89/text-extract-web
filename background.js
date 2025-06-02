/**
 * Text Extractor Extension - Background Service Worker
 * Handles message passing and extension lifecycle events
 */

/**
 * Handles extension installation or update
 */
chrome.runtime.onInstalled.addListener((details) => {
    try {
        if (details.reason === "install") {
            console.log("Extension installed");
            // Initialize default storage values
            chrome.storage.sync.set({
                'saved_selectors': [],
                'last_used_selectors': ['.card-body.question-body']
            });
        } else if (details.reason === "update") {
            console.log("Extension updated from", details.previousVersion);
            // Migrate storage data if needed between versions
        }
    } catch (error) {
        console.error('Error during extension installation/update:', error);
    }
});

// Listen for messages from content scripts or popup
chrome.runtime.onMessage.addListener(function(message, sender, sendResponse) {
    if (message && message.type) {
        console.log("Background received message type:", message.type);
    }

    // Always send a response to avoid hanging connections
    sendResponse({status: "received"});
    return false; // No async response needed
});

console.log('Background service worker initialized');
