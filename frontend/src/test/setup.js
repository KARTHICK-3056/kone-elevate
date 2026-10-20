import '@testing-library/jest-dom/vitest';
// jsdom has no real IndexedDB - the offline write queue (src/offline/*)
// needs one to be testable at all.
import 'fake-indexeddb/auto';

// jsdom does not implement page scrolling; navigation code scrolls to the top.
window.scrollTo = () => {};
