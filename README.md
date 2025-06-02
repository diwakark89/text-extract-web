# Text Extractor Chrome Extension

This Chrome extension allows users to extract text from web pages using CSS selectors. It's a useful tool for quickly grabbing content from specific elements on web pages.

## Features

- Extract text using custom CSS selectors
- Save frequently used selectors for quick access
- Copy extracted text to clipboard
- Multiple selector support for complex extractions

## Installation

1. Clone this repository or download the source code
2. Open Chrome and navigate to `chrome://extensions/`
3. Enable "Developer mode" in the top-right corner
4. Click "Load unpacked" and select the directory containing the extension files
5. The extension should now be installed and visible in your extensions list

## Usage

1. Navigate to any web page where you want to extract text
2. Click the Text Extractor extension icon in your Chrome toolbar
3. Enter one or more CSS selectors for the elements containing the text you want to extract
4. Click "Extract Text" to see the content
5. Use the "Copy Text" button to copy the extracted content to your clipboard

### Saving Selectors

- Click the save icon (💾) next to any selector to save it for future use
- Click "Manage Saved Selectors" to view, use, or delete your saved selectors

## Development

### Project Structure

- `manifest.json` - Extension configuration
- `popup.html` - UI for the extension popup
- `popup.js` - Logic for the popup interface
- `background.js` - Service worker for background processing
- `icons/` - Extension icons

### Technologies

- JavaScript (ES6+)
- Chrome Extension API
- Chrome Storage API for saving user preferences

## License

MIT License
