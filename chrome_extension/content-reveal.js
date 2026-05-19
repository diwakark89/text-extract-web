/**
 * Simulates various interactions on the page that might reveal hidden content
 * @returns {Promise<string>} - Message about what was done
 */
async function simulateRevealInteractions() {
  try {
    let interactionCount = 0;

    // 1. Find and click buttons that might reveal content
    const revealButtonSelectors = [
      // General buttons that show more content
      "button:not([disabled])",
      'a[role="button"]',
      '[role="button"]',
      ".show-more",
      ".read-more",
      ".load-more",
      ".expand",
      ".toggle",
      ".reveal",
      ".show-answer",
      '[aria-expanded="false"]',

      // Common text patterns in buttons that reveal content
      'button:contains("Show")',
      'button:contains("More")',
      'button:contains("Expand")',
      'button:contains("View")',
      'button:contains("Reveal")',
      'a:contains("Show")',
      'a:contains("More")',
      'a:contains("Expand")',
    ];

    // Click each type of reveal button
    for (const selector of revealButtonSelectors) {
      try {
        const buttons = document.querySelectorAll(selector);
        for (const btn of buttons) {
          // Check if this button might control hidden content
          const text = btn.textContent?.toLowerCase() || "";
          const mightReveal =
            text.includes("show") ||
            text.includes("more") ||
            text.includes("expand") ||
            text.includes("view") ||
            text.includes("reveal");

          if (mightReveal || btn.getAttribute("aria-expanded") === "false") {
            try {
              btn.click();
              interactionCount++;
              // Wait a bit between clicks
              await new Promise((r) => setTimeout(r, 50));
            } catch (e) {
              // Ignore errors for individual button clicks
            }
          }
        }
      } catch (e) {
        // Continue with other selectors if one fails
        console.warn(`Error with selector ${selector}:`, e);
      }
    }

    // 2. Set aria-expanded attributes to true
    document.querySelectorAll('[aria-expanded="false"]').forEach((el) => {
      try {
        el.setAttribute("aria-expanded", "true");
        interactionCount++;
      } catch (e) {
        // Ignore errors
      }
    });

    // 3. Try to make all hidden elements visible temporarily to extract their content
    const hiddenElements = Array.from(document.querySelectorAll("*")).filter(
      (el) => {
        const style = window.getComputedStyle(el);
        return style.display === "none";
      }
    );

    return `Performed ${interactionCount} interactions that might reveal content. Found ${hiddenElements.length} hidden elements.`;
  } catch (error) {
    console.error("Error during reveal interactions:", error);
    return "Error simulating reveal interactions";
  }
}

/**
 * Attempts to find and click "reveal" buttons near the specified selector
 * @param {string} selector - CSS selector to look near
 * @returns {Promise<string>} - Message about what was done
 */
async function handleRevealButtonClick(selector) {
  try {
    // Find potential reveal buttons
    const revealButtons = document.querySelectorAll(
      'button, a, .btn, [role="button"], [aria-expanded="false"], .show-more, .expand, .reveal, .toggle'
    );

    // Get the target elements based on the selector
    const targetElements = document.querySelectorAll(selector);

    if (!targetElements || targetElements.length === 0) {
      return "No target elements found with the provided selector";
    }

    // Find buttons that are near our target elements
    const relevantButtons = [];
    let clickCount = 0;

    targetElements.forEach((element) => {
      // Look for buttons inside the element
      element
        .querySelectorAll(
          'button, a, .btn, [role="button"], [aria-expanded="false"]'
        )
        .forEach((btn) => {
          relevantButtons.push(btn);
        });

      // Look for buttons in the parent element
      if (element.parentElement) {
        element.parentElement
          .querySelectorAll(
            'button, a, .btn, [role="button"], [aria-expanded="false"]'
          )
          .forEach((btn) => {
            if (!relevantButtons.includes(btn)) {
              relevantButtons.push(btn);
            }
          });
      }

      // Look for buttons that are siblings
      if (element.parentElement) {
        Array.from(element.parentElement.children).forEach((sibling) => {
          if (sibling !== element) {
            sibling
              .querySelectorAll(
                'button, a, .btn, [role="button"], [aria-expanded="false"]'
              )
              .forEach((btn) => {
                if (!relevantButtons.includes(btn)) {
                  relevantButtons.push(btn);
                }
              });
          }
        });
      }
    });

    // Filter for likely reveal buttons
    const revealButtonsToClick = relevantButtons.filter((btn) => {
      const text = btn.textContent?.toLowerCase() || "";
      const hasRevealText = [
        "show",
        "more",
        "reveal",
        "expand",
        "view",
        "see all",
        "read",
        "answer",
      ].some((keyword) => text.includes(keyword));
      const hasRevealAttr =
        btn.getAttribute("aria-expanded") === "false" ||
        btn.getAttribute("aria-controls") ||
        btn.classList.contains("show-more") ||
        btn.classList.contains("expand") ||
        btn.classList.contains("reveal");
      return hasRevealText || hasRevealAttr;
    });

    // Click the reveal buttons
    for (const btn of revealButtonsToClick) {
      try {
        btn.click();
        clickCount++;
        // Wait a bit for content to appear
        await new Promise((r) => setTimeout(r, 100));
      } catch (e) {
        console.warn("Failed to click reveal button:", e);
      }
    }

    return `Clicked ${clickCount} reveal buttons near selector ${selector}`;
  } catch (error) {
    console.error("Error handling reveal button clicks:", error);
    return "Error handling reveal button clicks";
  }
}

/**
 * This helper script provides advanced functionality to interact with "reveal" buttons
 * and extract hidden content on web pages
 */

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "clickRevealButtons") {
    handleRevealButtonClick(request.nearSelector)
      .then((result) => {
        sendResponse({
          success: true,
          message: result,
        });
      })
      .catch((error) => {
        sendResponse({
          success: false,
          error: error.message,
        });
      });
    return true; // Indicate async response
  } else if (request.action === "simulateRevealInteractions") {
    simulateRevealInteractions()
      .then((result) => {
        sendResponse({
          success: true,
          message: result,
        });
      })
      .catch((error) => {
        sendResponse({
          success: false,
          error: error.message,
        });
      });
    return true; // Indicate async response
  }
});
