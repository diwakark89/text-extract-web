/**
 * Content script for Question Text Extractor extension
 *
 * This script is injected into web pages to extract text from specified elements
 * using CSS selectors. It communicates with the popup via Chrome's messaging API.
 */

// Listen for messages from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "extractText") {
    if (
      !request.questionSelector ||
      !request.optionsSelector ||
      !request.answerSelector
    ) {
      sendResponse({
        success: false,
        error: "All three selectors (question, options, answer) are required",
      });
      return true;
    }

    const options = request.options || {};
    // Default to including hidden text if not specified
    const includeHiddenText = options.includeHiddenText !== false;
    const questionChildSelector = options.questionChildSelector || "";
    const optionsChildSelector = options.optionsChildSelector || "";
    const answerChildSelector = options.answerChildSelector || "";

    // Get examName, tagList, prompt, text-to-remove values, and selectors-to-remove if provided
    console.log("Request from popup:", request);
    const examName = request.examName || "";
    const tagList = request.tagList || [];
    const prompt = request.prompt || "";
    const textToRemoveValues = request.textToRemoveValues || [];
    const selectorsToRemove = request.selectorsToRemove || [];
    const parsedStartIndex = Number.parseInt(request.startIndex, 10);
    const startIndex =
      Number.isNaN(parsedStartIndex) || parsedStartIndex < 1
        ? 1
        : parsedStartIndex;

    console.log("Extracted parameters:", {
      examName,
      tagList,
      prompt,
      startIndex,
      textToRemoveValues,
      selectorsToRemove,
      questionChildSelector,
      optionsChildSelector,
      answerChildSelector,
    });

    // Extract text based on provided selectors and options
    extractTextFromSelectors(
      request.questionSelector,
      request.optionsSelector,
      request.answerSelector,
      {
        includeHiddenText,
        examName,
        tagList,
        prompt,
        startIndex,
        textToRemoveValues,
        selectorsToRemove,
        questionChildSelector,
        optionsChildSelector,
        answerChildSelector,
      },
    )
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
 * @param {string} questionSelector - CSS selector for questions
 * @param {string} optionsSelector - CSS selector for options
 * @param {string} answerSelector - CSS selector for answers
 * @param {Object} options - Extraction options
 * @param {boolean} options.includeHiddenText - Whether to include text from hidden elements
 * @param {string} options.questionChildSelector - Optional nested selector to extract question text from
 * @param {string} options.optionsChildSelector - Optional nested selector to extract options text from
 * @param {string} options.answerChildSelector - Optional nested selector to extract answer text from
 * @param {string} options.examName - Exam name to include with the extracted text
 * @param {string[]} options.tagList - Array of tags to include with the extracted text
 * @param {string} options.prompt - Prompt text to include with the extracted text
 * @param {number} options.startIndex - Starting index value to assign in output (1-based)
 * @param {string[]} options.textToRemoveValues - Array of text patterns to remove from the extracted content
 * @returns {Promise<string>} - Promise resolving to formatted extracted text
 */
async function extractTextFromSelectors(
  questionSelector,
  optionsSelector,
  answerSelector,
  options = {
    includeHiddenText: true,
    questionChildSelector: "",
    optionsChildSelector: "",
    answerChildSelector: "",
    examName: "",
    tagList: [],
    prompt: "",
    startIndex: 1,
    textToRemoveValues: [],
    selectorsToRemove: [],
  },
) {
  try {
    // First, if selectors-to-remove are specified, get their content to exclude later
    let contentToRemove = [];
    if (options.selectorsToRemove && options.selectorsToRemove.length > 0) {
      console.log("Processing selectors to remove:", options.selectorsToRemove);
      for (const selectorToRemove of options.selectorsToRemove) {
        if (!selectorToRemove) continue;
        console.log(`Processing selector to remove: ${selectorToRemove}`);

        try {
          const elementsToRemove = document.querySelectorAll(selectorToRemove);
          console.log(
            `Found ${elementsToRemove.length} elements matching selector: ${selectorToRemove}`,
          );
          if (elementsToRemove && elementsToRemove.length > 0) {
            // Extract text from each element that should be removed
            const textsFromSelector = Array.from(elementsToRemove)
              .map((el) => {
                const visibleText = el.innerText.trim();
                const hiddenText = extractHiddenText(el);
                const resultText = visibleText || hiddenText || "";
                if (resultText) {
                  console.log(
                    `Found text to remove (${resultText.length} chars): ${resultText.substring(0, 50)}${resultText.length > 50 ? "..." : ""}`,
                  );
                }
                return resultText;
              })
              .filter((text) => text.length > 0);

            console.log(
              `Extracted ${textsFromSelector.length} text items to remove from selector ${selectorToRemove}`,
            );
            // Add all texts from this selector to the master list
            contentToRemove = [...contentToRemove, ...textsFromSelector];
          }
        } catch (error) {
          console.error(
            `Error processing selector-to-remove ${selectorToRemove}:`,
            error,
          );
        }
      }
    }

    // Get all elements that match any of the three selectors
    const allElements = document.querySelectorAll(
      `${questionSelector}, ${optionsSelector}, ${answerSelector}`,
    );
    console.log(`Found ${allElements.length} total elements to process`);

    // Create a sequential scan through the page
    const mcqItems = [];
    let currentItem = null;

    function extractElementText(sourceElement, childSelector) {
      let targetElement = sourceElement;

      if (childSelector) {
        try {
          targetElement = sourceElement.querySelector(childSelector);
        } catch (error) {
          console.error(`Invalid child selector: ${childSelector}`, error);
          return "";
        }

        if (!targetElement) {
          return "";
        }
      }

      const visibleText = targetElement.innerText.trim();
      if (visibleText) {
        return visibleText;
      }

      if (options.includeHiddenText) {
        return extractHiddenText(targetElement) || "";
      }

      return "";
    }

    for (let i = 0; i < allElements.length; i++) {
      const element = allElements[i];

      // Check which type of element this is
      const isQuestion = element.matches(questionSelector);
      const isOption = element.matches(optionsSelector);
      const isAnswer = element.matches(answerSelector);

      if (isQuestion) {
        // Save the previous item if it exists
        if (
          currentItem &&
          (currentItem.question || currentItem.options.length > 0)
        ) {
          mcqItems.push(currentItem);
        }

        // Start a new item
        const questionText = extractElementText(
          element,
          options.questionChildSelector,
        );
        currentItem = {
          question: questionText,
          options: [],
          answers: [],
        };
        console.log(
          `Found question ${mcqItems.length + 1}: ${currentItem.question.substring(0, 50)}...`,
        );
      } else if (isOption && currentItem) {
        // Add option to current item
        const optionText = extractElementText(
          element,
          options.optionsChildSelector,
        );

        // Try to split options by common delimiters if it contains multiple options
        const optionLines = optionText
          .split(/\n/)
          .filter((line) => line.trim().length > 0);

        // If we have multiple lines that look like options (e.g., start with A., B., etc.), use them
        if (
          optionLines.length > 1 &&
          optionLines.some((line) => /^[A-Za-z][\.):\.]/.test(line.trim()))
        ) {
          optionLines.forEach((line) => currentItem.options.push(line.trim()));
          console.log(
            `  Added ${optionLines.length} options to current question`,
          );
        } else if (optionText) {
          // Otherwise, treat the whole text as a single option
          currentItem.options.push(optionText);
          console.log(
            `  Added option to current question: ${optionText.substring(0, 30)}...`,
          );
        }
      } else if (isAnswer && currentItem) {
        // Add answer to current item
        const answerText = extractElementText(
          element,
          options.answerChildSelector,
        );

        if (answerText) {
          // Store the raw answer text - parsing will happen later
          currentItem.answers.push(answerText);
          console.log(`  Added answer to current question: ${answerText}`);
        }
      }
    }

    // Don't forget to add the last item
    if (
      currentItem &&
      (currentItem.question || currentItem.options.length > 0)
    ) {
      mcqItems.push(currentItem);
    }

    console.log(`Total items created: ${mcqItems.length}`);

    // Process text-to-remove patterns and selectors-to-remove on each item

    // Helper function to clean text
    function cleanText(text, contentToRemove, textToRemoveValues) {
      let cleanedText = text;

      // Remove content from selectors-to-remove
      if (contentToRemove && contentToRemove.length > 0) {
        contentToRemove.forEach((content) => {
          if (content) {
            try {
              const safePattern = content.replace(
                /[.*+?^${}()|[\]\\]/g,
                "\\$&",
              );
              const regex = new RegExp(safePattern, "gi");
              cleanedText = cleanedText.replace(regex, "");
            } catch (e) {
              cleanedText = cleanedText.split(content).join("");
            }
          }
        });
      }

      // Remove text-to-remove patterns
      if (textToRemoveValues && textToRemoveValues.length > 0) {
        textToRemoveValues.forEach((pattern) => {
          if (pattern) {
            try {
              const safePattern = pattern.replace(
                /[.*+?^${}()|[\]\\]/g,
                "\\$&",
              );
              cleanedText = cleanedText.replace(
                new RegExp(safePattern, "g"),
                "",
              );
            } catch (e) {
              cleanedText = cleanedText.split(pattern).join("");
            }
          }
        });
      }

      return cleanedText.trim();
    }

    // Clean each item's text
    mcqItems.forEach((item) => {
      item.question = cleanText(
        item.question,
        contentToRemove,
        options.textToRemoveValues,
      );
      item.options = item.options
        .map((opt) =>
          cleanText(opt, contentToRemove, options.textToRemoveValues),
        )
        .filter((opt) => opt.length > 0);
      item.answers = item.answers
        .map((ans) =>
          cleanText(ans, contentToRemove, options.textToRemoveValues),
        )
        .filter((ans) => ans.length > 0);
    });

    // Helper function to parse options into A, B, C, D format
    function parseOptionsToObject(optionsArray) {
      const optionsObject = {};
      const labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"];

      optionsArray.forEach((option, index) => {
        if (index < labels.length) {
          // Remove leading letters/numbers if they exist (e.g., "A. text" -> "text")
          let cleanOption = option
            .replace(/^[A-Za-z0-9][\.):\.\s]+/, "")
            .trim();
          optionsObject[labels[index]] = cleanOption || option;
        }
      });

      return optionsObject;
    }

    // Helper function to parse answers to array format
    function parseAnswersToArray(answersArray) {
      const answerLetters = [];

      function addAnswerLetter(letter) {
        const normalizedLetter = letter.toUpperCase();
        if (!answerLetters.includes(normalizedLetter)) {
          answerLetters.push(normalizedLetter);
        }
      }

      answersArray.forEach((answer) => {
        // Remove extra whitespace
        const cleanAnswer = answer.trim();

        if (!cleanAnswer) return;

        // First check if it's ONLY a single letter (A, B, C, etc.) or letter with punctuation
        const singleLetterMatch = cleanAnswer.match(/^([A-J])[\.\):\s]*$/i);
        if (singleLetterMatch) {
          addAnswerLetter(singleLetterMatch[1]);
          return;
        }

        // Check if answer contains comma-separated values (e.g., "A,C" or "A, C")
        if (cleanAnswer.includes(",")) {
          const parts = cleanAnswer.split(",").map((p) => p.trim());
          parts.forEach((part) => {
            // Match only single letters (A-J) followed by optional punctuation/space
            const match = part.match(/^([A-J])[\.\):\s]*$/i);
            if (match) {
              addAnswerLetter(match[1]);
            }
          });
        }

        // Support compact multi-answer formats like "AE", plus connectors like "A and E".
        const normalizedAnswer = cleanAnswer
          .toUpperCase()
          .replace(/CORRECT\s*ANSWER[:\-\s]*/gi, "")
          .replace(/\bAND\b/gi, ",")
          .replace(/&/g, ",")
          .trim();
        const compactLetters = normalizedAnswer.replace(
          /[\s,;|/\\\-_.():]+/g,
          "",
        );

        if (/^[A-J]+$/.test(compactLetters)) {
          compactLetters.split("").forEach((letter) => {
            addAnswerLetter(letter);
          });
          return;
        }

        // Fallback for patterns like "A) correct option"
        const leadingLetterMatch = cleanAnswer.match(/^([A-J])[\.\):\s]/i);
        if (leadingLetterMatch) {
          addAnswerLetter(leadingLetterMatch[1]);
        }
      });

      return answerLetters.length > 0 ? answerLetters : []; // Return empty array if no answer found
    }

    const normalizedStartIndex =
      Number.isInteger(options.startIndex) && options.startIndex > 0
        ? options.startIndex
        : 1;

    // Convert items to the new format
    const formattedItems = mcqItems
      .map((item, index) => {
        return {
          index: normalizedStartIndex + index,
          question: item.question || "",
          options: parseOptionsToObject(item.options),
          correct_answers: parseAnswersToArray(item.answers),
        };
      })
      .filter(
        (item) =>
          item.question.length > 0 || Object.keys(item.options).length > 0,
      );

    // If no items were found, return empty array with message
    if (formattedItems.length === 0) {
      return JSON.stringify(
        [
          {
            index: normalizedStartIndex,
            question: "No content found with the provided selectors.",
            options: {},
            correct_answers: [],
          },
        ],
        null,
        2,
      );
    }

    // Convert to JSON string with formatting
    const jsonString = JSON.stringify(formattedItems, null, 2);
    return jsonString;
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
