const initialBrowserData = JSON.parse(document.getElementById("browser-events").textContent);
const browserConfig = JSON.parse(document.getElementById("browser-config").textContent);
const browserEventList = document.getElementById("browser-event-list");
const browserMessage = document.getElementById("browser-message");
const browserSelectButton = document.getElementById("browser-select-button");
const browserMoveButton = document.getElementById("browser-move-button");
const browserDownloadButton = document.getElementById("browser-download-button");
const browserDeleteButton = document.getElementById("browser-delete-button");
const browserSlideshowButton = document.getElementById("browser-slideshow-button");
const browserSlideshowSpeed = document.getElementById("browser-slideshow-speed");
const browserDaySelect = document.getElementById("browser-day-select");
const browserDaySummary = document.getElementById("browser-day-summary");

const initialEvents = Array.isArray(initialBrowserData)
  ? initialBrowserData
  : Array.isArray(initialBrowserData.events)
    ? initialBrowserData.events
    : [];

let browserEvents = initialEvents;
let browserDayGroups = [];
let browserAvailableDays = Array.isArray(initialBrowserData.day_groups)
  ? initialBrowserData.day_groups
  : [];
let selectedBrowserDayKey =
  typeof initialBrowserData.selected_day_key === "string"
    ? initialBrowserData.selected_day_key
    : null;
const selectedBrowserFilenames = new Set();
const defaultSelectButtonLabel = browserConfig.selectButtonLabel || "Select Photo";
const defaultSelectedButtonLabel = browserConfig.selectedButtonLabel || "Selected";
const defaultOpenButtonLabel = browserConfig.openButtonLabel || "Open Full Image";

function filenameFromEvent(event) {
  return event.snapshot_url.split("/").pop() || "motion-event.jpg";
}

function formatPhotoCount(count) {
  return `${count} photo${count === 1 ? "" : "s"}`;
}

function dayKeyFromEvent(event) {
  if (typeof event.detected_at === "string" && event.detected_at.length >= 10) {
    return event.detected_at.slice(0, 10);
  }
  return "unknown-day";
}

function dayLabelFromKey(dayKey) {
  if (dayKey === "unknown-day") {
    return "Unknown Day";
  }
  const date = new Date(`${dayKey}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) {
    return dayKey;
  }
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

function buildDayGroupsFromEvents(events) {
  const grouped = new Map();
  for (const event of events) {
    const dayKey = dayKeyFromEvent(event);
    if (!grouped.has(dayKey)) {
      grouped.set(dayKey, {
        day_key: dayKey,
        label: dayLabelFromKey(dayKey),
        events: [],
      });
    }
    grouped.get(dayKey).events.push(event);
  }
  return Array.from(grouped.values()).map((group) => ({
    day_key: group.day_key,
    label: group.label,
    event_count: group.events.length,
    events: group.events,
  }));
}

function normalizeDayGroups(dayGroups, events) {
  if (!Array.isArray(dayGroups) || !dayGroups.length) {
    return buildDayGroupsFromEvents(events);
  }

  return dayGroups
    .map((group) => {
      const groupEvents = Array.isArray(group.events) ? group.events : [];
      const dayKey =
        typeof group.day_key === "string" && group.day_key
          ? group.day_key
          : dayKeyFromEvent(groupEvents[0] || {});
      return {
        day_key: dayKey,
        label:
          typeof group.label === "string" && group.label
            ? group.label
            : dayLabelFromKey(dayKey),
        event_count: groupEvents.length,
        events: groupEvents,
      };
    })
    .filter((group) => group.events.length > 0);
}

function normalizeAvailableDayGroups(dayGroups) {
  if (!Array.isArray(dayGroups)) {
    return [];
  }

  return dayGroups
    .map((group) => {
      const dayKey = typeof group.day_key === "string" ? group.day_key : "unknown-day";
      const eventCount = Number.isFinite(group.event_count) ? Number(group.event_count) : 0;
      return {
        day_key: dayKey,
        label:
          typeof group.label === "string" && group.label
            ? group.label
            : dayLabelFromKey(dayKey),
        event_count: Math.max(Math.trunc(eventCount), 0),
      };
    })
    .filter((group) => group.event_count > 0);
}

function selectedBrowserDayGroup() {
  return browserAvailableDays.find((group) => group.day_key === selectedBrowserDayKey) || null;
}

function syncDayBrowseControls() {
  if (!browserConfig.dayBrowseEnabled || !browserDaySelect) {
    return;
  }

  const hasDays = browserAvailableDays.length > 0;
  browserDaySelect.innerHTML = "";

  for (const group of browserAvailableDays) {
    const option = document.createElement("option");
    option.value = group.day_key;
    option.textContent = `${group.label} (${group.event_count})`;
    option.selected = group.day_key === selectedBrowserDayKey;
    browserDaySelect.append(option);
  }

  browserDaySelect.disabled = !hasDays;
  if (!hasDays) {
    selectedBrowserDayKey = null;
  } else if (!selectedBrowserDayGroup()) {
    selectedBrowserDayKey = browserAvailableDays[0].day_key;
    browserDaySelect.value = selectedBrowserDayKey;
  }

  if (browserDaySummary) {
    const selectedDay = selectedBrowserDayGroup();
    browserDaySummary.textContent = selectedDay
      ? `Showing ${formatPhotoCount(browserEvents.length)} from ${selectedDay.label}.`
      : "No saved motion events yet.";
  }
}

function browserListUrl() {
  const url = new URL(browserConfig.listUrl, window.location.origin);
  if (browserConfig.dayBrowseEnabled && selectedBrowserDayKey) {
    url.searchParams.set("day", selectedBrowserDayKey);
  }
  return `${url.pathname}${url.search}`;
}

function currentSlideshowIntervalMs() {
  if (browserSlideshowSpeed && browserSlideshowSpeed.value) {
    const seconds = Number.parseFloat(browserSlideshowSpeed.value);
    if (Number.isFinite(seconds)) {
      return Math.max(Math.round(seconds * 1000), 500);
    }
  }
  const fallbackSeconds = Number(browserConfig.defaultSlideshowSpeedSeconds || 2);
  return Math.max(Math.round(fallbackSeconds * 1000), 500);
}

function syncSlideshowControls(isRunning) {
  if (browserSlideshowButton) {
    browserSlideshowButton.disabled = !browserEvents.length;
    browserSlideshowButton.textContent = isRunning ? "Stop Slideshow" : "Start Slideshow";
  }
  if (browserSlideshowSpeed) {
    browserSlideshowSpeed.disabled = isRunning || !browserEvents.length;
  }
}

function createEventLightbox({
  moveButtonLabel,
  onMove,
  slideshowEnabled = false,
  getSlideshowIntervalMs = null,
  onSlideshowStateChange = null,
}) {
  const overlay = document.createElement("div");
  overlay.className = "lightbox hidden";

  const dialog = document.createElement("div");
  dialog.className = "lightbox-dialog";

  const controls = document.createElement("div");
  controls.className = "lightbox-controls";

  const previousButton = document.createElement("button");
  previousButton.type = "button";
  previousButton.textContent = "Previous";

  const nextButton = document.createElement("button");
  nextButton.type = "button";
  nextButton.textContent = "Next";

  const slideshowButton = document.createElement("button");
  slideshowButton.type = "button";
  slideshowButton.textContent = "Start Slideshow";

  const moveButton = document.createElement("button");
  moveButton.type = "button";
  moveButton.textContent = moveButtonLabel || "Move";

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.textContent = "Close";

  const image = document.createElement("img");
  image.className = "lightbox-image";
  image.alt = "";

  const caption = document.createElement("p");
  caption.className = "lightbox-caption";

  controls.append(previousButton, nextButton);
  if (slideshowEnabled) {
    controls.append(slideshowButton);
  }
  if (onMove) {
    controls.append(moveButton);
  }
  controls.append(closeButton);
  dialog.append(controls, image, caption);
  overlay.append(dialog);
  document.body.append(overlay);

  let items = [];
  let currentIndex = 0;
  let slideshowTimer = null;

  function notifySlideshowState() {
    const running = slideshowTimer !== null;
    if (slideshowEnabled) {
      slideshowButton.textContent = running ? "Stop Slideshow" : "Start Slideshow";
    }
    if (typeof onSlideshowStateChange === "function") {
      onSlideshowStateChange(running);
    }
  }

  function currentItem() {
    return items[currentIndex] || null;
  }

  function setItems(nextItems) {
    items = Array.isArray(nextItems) ? nextItems : [];
    if (!items.length) {
      currentIndex = 0;
      return;
    }
    currentIndex = Math.min(currentIndex, items.length - 1);
  }

  function showIndex(index) {
    if (!items.length) {
      close();
      return;
    }
    currentIndex = (index + items.length) % items.length;
    const event = currentItem();
    image.src = `${event.snapshot_url}?t=${Date.now()}`;
    image.alt = `Saved photo ${event.detected_at}`;
    caption.textContent = `${new Date(event.detected_at).toLocaleString()} - ${filenameFromEvent(event)}`;
  }

  function stopSlideshow() {
    if (slideshowTimer !== null) {
      window.clearInterval(slideshowTimer);
      slideshowTimer = null;
      notifySlideshowState();
    }
  }

  function startSlideshow() {
    if (!items.length) {
      return;
    }
    stopSlideshow();
    slideshowTimer = window.setInterval(() => {
      if (!items.length) {
        close();
        return;
      }
      showIndex(currentIndex + 1);
    }, getSlideshowIntervalMs ? getSlideshowIntervalMs() : 2000);
    notifySlideshowState();
  }

  function close() {
    stopSlideshow();
    overlay.classList.add("hidden");
    image.removeAttribute("src");
    document.body.classList.remove("lightbox-open");
  }

  function open(nextItems, startIndex) {
    setItems(nextItems);
    if (!items.length) {
      close();
      return;
    }
    overlay.classList.remove("hidden");
    document.body.classList.add("lightbox-open");
    showIndex(startIndex);
  }

  function showPrevious() {
    showIndex(currentIndex - 1);
  }

  function showNext() {
    showIndex(currentIndex + 1);
  }

  previousButton.addEventListener("click", showPrevious);
  nextButton.addEventListener("click", showNext);
  closeButton.addEventListener("click", close);
  if (slideshowEnabled) {
    slideshowButton.addEventListener("click", () => {
      if (slideshowTimer !== null) {
        stopSlideshow();
      } else {
        startSlideshow();
      }
    });
  }
  if (onMove) {
    moveButton.addEventListener("click", async () => {
      const event = currentItem();
      if (!event) {
        return;
      }
      moveButton.disabled = true;
      try {
        await onMove(event, {
          close,
          open,
          currentIndex: () => currentIndex,
        });
      } finally {
        moveButton.disabled = false;
      }
    });
  }
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) {
      close();
    }
  });
  window.addEventListener("keydown", (event) => {
    if (overlay.classList.contains("hidden")) {
      return;
    }
    if (event.key === "Escape") {
      close();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      showPrevious();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      showNext();
    }
  });

  notifySlideshowState();
  return {
    open,
    close,
    currentIndex: () => currentIndex,
    startSlideshow(nextItems, startIndex = 0) {
      open(nextItems, startIndex);
      startSlideshow();
    },
    stopSlideshow,
    isSlideshowRunning() {
      return slideshowTimer !== null;
    },
  };
}

const browserLightbox = createEventLightbox({
  moveButtonLabel: browserConfig.moveButtonLabel,
  onMove: browserConfig.moveUrl ? moveCurrentLightboxEventToGallery : null,
  slideshowEnabled: Boolean(browserConfig.slideshowEnabled),
  getSlideshowIntervalMs: currentSlideshowIntervalMs,
  onSlideshowStateChange: syncSlideshowControls,
});

function updateBrowserActionButtons() {
  const totalEvents = browserEvents.length;
  const selectedCount = selectedBrowserFilenames.size;
  const hasEvents = totalEvents > 0;
  const hasSelection = selectedCount > 0;

  browserSelectButton.disabled = !hasEvents;
  if (browserMoveButton) {
    browserMoveButton.disabled = !hasSelection || !browserConfig.moveUrl;
  }
  browserDownloadButton.disabled = !hasSelection;
  browserDeleteButton.disabled = !hasSelection;
  browserSelectButton.textContent =
    hasEvents && selectedCount === totalEvents ? "Clear Selection" : "Select All";
  syncSlideshowControls(browserLightbox.isSlideshowRunning());
  syncDayBrowseControls();
}

function createEventCard(index, event) {
  const filename = filenameFromEvent(event);
  const prioritizeSelection = Boolean(browserConfig.prioritizeSelection);
  const card = document.createElement("article");
  card.className = "event-card";

  const imagePreview = document.createElement("div");
  imagePreview.className = "event-image-link event-image-preview";

  const openPreviewButton = document.createElement("button");
  openPreviewButton.type = "button";
  openPreviewButton.className = "event-open";
  openPreviewButton.textContent = defaultOpenButtonLabel;
  openPreviewButton.addEventListener("click", () => {
    browserLightbox.open(browserEvents, index);
  });

  const img = document.createElement("img");
  img.src = `${event.snapshot_url}?max_w=480&max_h=360&quality=70&t=${Date.now()}`;
  img.alt = `Saved photo ${event.detected_at}`;
  img.loading = "lazy";
  imagePreview.append(img);

  const body = document.createElement("div");
  body.className = "event-card-body";

  const selection = document.createElement("button");
  selection.className = "event-select";
  selection.type = "button";

  if (prioritizeSelection) {
    const previewControls = document.createElement("div");
    previewControls.className = "event-preview-controls";
    selection.classList.add("event-select-priority");
    previewControls.append(selection);
    imagePreview.append(previewControls);
  }

  function syncSelectionState() {
    const isSelected = selectedBrowserFilenames.has(filename);
    selection.classList.toggle("selected", isSelected);
    selection.setAttribute("aria-pressed", isSelected ? "true" : "false");
    selection.textContent = isSelected
      ? defaultSelectedButtonLabel
      : defaultSelectButtonLabel;
    card.classList.toggle("selected", isSelected);
  }

  selection.addEventListener("click", () => {
    if (selectedBrowserFilenames.has(filename)) {
      selectedBrowserFilenames.delete(filename);
    } else {
      selectedBrowserFilenames.add(filename);
    }
    syncSelectionState();
    updateBrowserActionButtons();
  });
  syncSelectionState();

  const title = document.createElement("h3");
  title.textContent = new Date(event.detected_at).toLocaleString();

  const path = document.createElement("p");
  path.className = "subtle";
  path.textContent = filename;

  const actions = document.createElement("div");
  actions.className = "event-card-actions";

  actions.append(openPreviewButton);

  const download = document.createElement("a");
  download.className = "event-download";
  download.href = event.snapshot_url;
  download.download = filename;
  download.textContent = "Download JPG";

  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "danger";
  removeButton.textContent = "Delete";
  removeButton.addEventListener("click", () => {
    void deleteBrowserEvents([filename]);
  });

  actions.append(download, removeButton);
  if (prioritizeSelection) {
    body.append(title, path, actions);
  } else {
    body.append(selection, title, path, actions);
  }
  card.append(imagePreview, body);
  return card;
}

function renderDayGroups(dayGroups) {
  const indexByFilename = new Map(browserEvents.map((event, index) => [filenameFromEvent(event), index]));
  for (const group of dayGroups) {
    const section = document.createElement("section");
    section.className = "browser-day-group";

    const header = document.createElement("div");
    header.className = "browser-day-group-header";

    const title = document.createElement("h2");
    title.className = "browser-day-group-title";
    title.textContent = group.label;

    const meta = document.createElement("p");
    meta.className = "subtle browser-day-group-meta";
    meta.textContent = formatPhotoCount(group.event_count);

    header.append(title, meta);
    section.append(header);

    const list = document.createElement("div");
    list.className = "event-list";
    for (const event of group.events) {
      const index = indexByFilename.get(filenameFromEvent(event));
      if (index !== undefined) {
        list.append(createEventCard(index, event));
      }
    }
    section.append(list);
    browserEventList.append(section);
  }
}

function renderBrowserEvents(events, dayGroups = null) {
  browserEvents = events;
  if (browserConfig.dayBrowseEnabled) {
    browserAvailableDays = normalizeAvailableDayGroups(dayGroups);
    if (
      browserAvailableDays.length > 0 &&
      !browserAvailableDays.some((group) => group.day_key === selectedBrowserDayKey)
    ) {
      selectedBrowserDayKey = browserAvailableDays[0].day_key;
    }
    browserDayGroups = [];
  } else {
    browserDayGroups = browserConfig.groupByDay ? normalizeDayGroups(dayGroups, events) : [];
  }

  const eventFilenames = new Set(events.map(filenameFromEvent).filter(Boolean));
  for (const filename of Array.from(selectedBrowserFilenames)) {
    if (!eventFilenames.has(filename)) {
      selectedBrowserFilenames.delete(filename);
    }
  }

  browserEventList.innerHTML = "";
  if (!events.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = browserConfig.emptyMessage;
    browserEventList.append(empty);
    updateBrowserActionButtons();
    return;
  }

  if (browserConfig.groupByDay && !browserConfig.dayBrowseEnabled) {
    renderDayGroups(browserDayGroups);
  } else {
    for (const [index, event] of events.entries()) {
      browserEventList.append(createEventCard(index, event));
    }
  }

  updateBrowserActionButtons();
}

async function refreshBrowserEvents() {
  const response = await fetch(browserListUrl());
  const payload = await response.json();
  if (!response.ok) {
    browserMessage.textContent = payload.error || browserConfig.refreshErrorMessage;
    return;
  }

  if (typeof payload.selected_day_key === "string" || payload.selected_day_key === null) {
    selectedBrowserDayKey = payload.selected_day_key;
  }
  renderBrowserEvents(payload.events || [], payload.day_groups || null);
}

async function downloadBrowserEvents(filenames) {
  if (!filenames.length) {
    browserMessage.textContent = "Select at least one photo.";
    return;
  }

  browserMessage.textContent = "Preparing download...";
  const response = await fetch(browserConfig.downloadUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filenames, day_key: selectedBrowserDayKey }),
  });

  if (!response.ok) {
    const payload = await response.json();
    browserMessage.textContent = payload.error || browserConfig.downloadErrorMessage;
    return;
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  const contentDisposition = response.headers.get("Content-Disposition") || "";
  const match = contentDisposition.match(/filename="?([^"]+)"?/);
  link.href = url;
  link.download = match ? match[1] : "motionsense-photos.zip";
  document.body.append(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
  browserMessage.textContent = `Downloaded ${formatPhotoCount(filenames.length)}.`;
}

async function deleteBrowserEvents(filenames) {
  if (!filenames.length) {
    browserMessage.textContent = "Select at least one photo.";
    return;
  }
  if (!window.confirm(`Delete ${formatPhotoCount(filenames.length)}?`)) {
    return;
  }

  browserMessage.textContent = browserConfig.deleteProgressMessage;
  const response = await fetch(browserConfig.deleteUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filenames }),
  });
  const payload = await response.json();

  if (!response.ok) {
    browserMessage.textContent = payload.error || browserConfig.deleteErrorMessage;
    return;
  }

  if (typeof payload.selected_day_key === "string" || payload.selected_day_key === null) {
    selectedBrowserDayKey = payload.selected_day_key;
  }
  for (const filename of filenames) {
    selectedBrowserFilenames.delete(filename);
  }
  renderBrowserEvents(payload.events || payload.gallery || [], payload.day_groups || null);
  browserMessage.textContent = `Deleted ${formatPhotoCount(payload.deleted_count)}.`;
}

async function moveBrowserEventsToGallery(filenames) {
  if (!browserConfig.moveUrl || !filenames.length) {
    return false;
  }

  browserMessage.textContent = browserConfig.moveProgressMessage;
  const response = await fetch(browserConfig.moveUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filenames, day_key: selectedBrowserDayKey }),
  });
  const payload = await response.json();

  if (!response.ok) {
    browserMessage.textContent = payload.error || browserConfig.moveErrorMessage;
    return false;
  }

  if (typeof payload.selected_day_key === "string" || payload.selected_day_key === null) {
    selectedBrowserDayKey = payload.selected_day_key;
  }
  for (const filename of filenames) {
    selectedBrowserFilenames.delete(filename);
  }
  renderBrowserEvents(payload.events || [], payload.day_groups || null);
  browserMessage.textContent = `Moved ${formatPhotoCount(payload.moved_count)} to gallery.`;
  return true;
}

async function moveCurrentLightboxEventToGallery(event, { close, open, currentIndex }) {
  const filename = filenameFromEvent(event);
  const nextIndex = currentIndex();
  const moved = await moveBrowserEventsToGallery([filename]);
  if (!moved) {
    return;
  }
  if (!browserEvents.length) {
    close();
    return;
  }
  open(browserEvents, Math.min(nextIndex, browserEvents.length - 1));
}

browserSelectButton.addEventListener("click", () => {
  if (selectedBrowserFilenames.size === browserEvents.length) {
    selectedBrowserFilenames.clear();
  } else {
    for (const event of browserEvents) {
      const filename = filenameFromEvent(event);
      if (filename) {
        selectedBrowserFilenames.add(filename);
      }
    }
  }
  renderBrowserEvents(browserEvents, browserDayGroups);
});

if (browserMoveButton) {
  browserMoveButton.addEventListener("click", () => {
    void moveBrowserEventsToGallery(Array.from(selectedBrowserFilenames));
  });
}

if (browserSlideshowButton) {
  browserSlideshowButton.addEventListener("click", () => {
    if (browserLightbox.isSlideshowRunning()) {
      browserLightbox.stopSlideshow();
      return;
    }
    if (!browserEvents.length) {
      return;
    }
    browserLightbox.startSlideshow(browserEvents, 0);
  });
}

if (browserDaySelect) {
  browserDaySelect.addEventListener("change", () => {
    selectedBrowserDayKey = browserDaySelect.value || null;
    selectedBrowserFilenames.clear();
    void refreshBrowserEvents();
  });
}

browserDownloadButton.addEventListener("click", () => {
  void downloadBrowserEvents(Array.from(selectedBrowserFilenames));
});

browserDeleteButton.addEventListener("click", () => {
  void deleteBrowserEvents(Array.from(selectedBrowserFilenames));
});

renderBrowserEvents(initialEvents, browserAvailableDays);
window.setInterval(() => {
  void refreshBrowserEvents();
}, 15000);
