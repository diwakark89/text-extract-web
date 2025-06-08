/**
 * Content script for Question Text Extractor extension
 *
 * This script is injected into web pages to extract text from specified elements
 * using CSS selectors. It communicates with the popup via Chrome's messaging API.
 */

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log("Content script received message:", request);

  if (request.action === "extractText") {
    if (!request.selectors || !Array.isArray(request.selectors)) {
      sendResponse({
        success: false,
        error: "Invalid selectors provided",
      });
      return true;
    }

    const options = request.options || {};
    // Default to including hidden text if not specified
    const includeHiddenText = options.includeHiddenText !== false;

    // Extract text based on provided selectors and options
    extractTextFromSelectors(request.selectors, { includeHiddenText })
      .then((result) => {
        sendResponse({
          success: true,
          data: result,
        });
      })
      .catch((error) => {
        sendResponse({
          success: false,
          error: error.message || "Unknown error during extraction",
        });
      });

    // Return true to indicate we'll respond asynchronously
    return true;
  } else {
    // Send response for unsupported actions
    sendResponse({
      success: false,
      error: "Unsupported action",
    });
    return false;
  }
});

/**
 * Extracts text from DOM elements matching the provided CSS selectors
 * @param {string[]} selectors - Array of CSS selectors to target
 * @param {Object} options - Extraction options
 * @param {boolean} options.includeHiddenText - Whether to include text from hidden elements
 * @returns {Promise<string>} - Promise resolving to formatted extracted text
 */
async function extractTextFromSelectors(
  selectors,
  options = { includeHiddenText: true }
) {
  try {
    let allExtractedText = [];

    // Process each selector
    for (const selector of selectors) {
      try {
        // Find all elements matching the selector
        const elements = document.querySelectorAll(selector);

        // Step 1: Try to reveal hidden content first
        await attemptToRevealHiddenContent(elements);

        // Step 2: Extract text from each element, including hidden ones
        const extractedText = Array.from(elements)
          .map((el) => {
            // Always try to get both hidden and visible content
            const visibleText = el.innerText.trim();
            const hiddenText = extractHiddenText(el);

            // Combine all text, using visible text if available
            return visibleText || hiddenText || "";
          })
          .filter((text) => text.length > 0);

        // Step 3: Look for additional hidden elements within parent containers
        const parentElements = new Set();
        elements.forEach((el) => {
          if (el.parentElement) parentElements.add(el.parentElement);
        });



        // Format and add the main extracted text
        if (extractedText.length > 0) {
          let output = `[Selector: ${selector}]\n${extractedText.join("\n\n")}`;

          allExtractedText.push(output);
        }
      } catch (error) {
        console.error(`Error with selector ${selector}:`, error);
      }
    }

    return (
      allExtractedText.join("\n\n---\n\n") ||
      "No content found with the provided selectors."
    );
  } catch (error) {
    console.error("Error extracting text:", error);
    throw error;
  }
}

/**
 * Attempts to reveal hidden content by interacting with "reveal" buttons
 * @param {NodeList} elements - Elements to check for reveal buttons
 * @returns {Promise<void>}
 */
async function attemptToRevealHiddenContent(elements) {
  try {

    const relevantButtons = [];

    // Find buttons that might reveal content near our elements
    elements.forEach((element) => {
      // Check for buttons within the element
      element
        .querySelectorAll('button, a, .btn, [role="button"]')
        .forEach((btn) => {
          relevantButtons.push(btn);
        });

      // Check for buttons that are siblings
      if (element.parentElement) {
        element.parentElement
          .querySelectorAll('button, a, .btn, [role="button"]')
          .forEach((btn) => {
            if (!relevantButtons.includes(btn)) {
              relevantButtons.push(btn);
            }
          });
      }
    });

    // Filter for likely reveal buttons
    const revealButtons = relevantButtons.filter((btn) => {
      const text = btn.textContent?.toLowerCase() || "";
      const hasRevealText = [
        "show",
        "more",
        "reveal",
        "expand",
        "view",
        "see all",
        "read",
      ].some((keyword) => text.includes(keyword));
      const hasRevealAttr =
        btn.getAttribute("aria-expanded") === "false" ||
        btn.getAttribute("aria-controls") ||
        btn.classList.contains("show-more") ||
        btn.classList.contains("expand");
      return hasRevealText || hasRevealAttr;
    });

    // Click the reveal buttons
    for (const btn of revealButtons) {
      try {
        btn.click();
        // Wait a bit for content to appear
        await new Promise((r) => setTimeout(r, 100));
      } catch (e) {
        console.warn("Failed to click reveal button:", e);
      }
    }
  } catch (error) {
    console.error("Error revealing hidden content:", error);
  }
}

/**
 * Extracts text from hidden elements
 * @param {HTMLElement} element - Element to extract hidden text from
 * @returns {string} - Extracted text content
 */
function extractHiddenText(element) {
  // Check for hidden content
  let hiddenContent = "";

  // Try several methods to get hidden text
  const isHidden = window.getComputedStyle(element).display === "none";

  if (isHidden) {
    // Method 1: Get textContent (works for hidden elements)
    hiddenContent = element.textContent?.trim() || "";

    // Method 2: If no text content, try to extract from HTML
    if (!hiddenContent) {
      hiddenContent =
        element.innerHTML
          ?.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "") // Remove style tags
          .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, "") // Remove script tags
          .replace(/<[^>]*>/g, " ") // Replace tags with spaces
          .replace(/\s+/g, " ") // Normalize whitespace
          .trim() || "";
    }
  }

  return hiddenContent;
}
