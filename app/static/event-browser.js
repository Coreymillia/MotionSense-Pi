const initialEvents = JSON.parse(document.getElementById("browser-events").textContent);
const browserConfig = JSON.parse(document.getElementById("browser-config").textContent);
const browserEventList = document.getElementById("browser-event-list");
const browserMessage = document.getElementById("browser-message");
const browserSelectButton = document.getElementById("browser-select-button");
const browserDownloadButton = document.getElementById("browser-download-button");
const browserDeleteButton = document.getElementById("browser-delete-button");

let browserEvents = initialEvents;
const selectedBrowserFilenames = new Set();
const browserLightbox = createEventLightbox({
  moveButtonLabel: browserConfig.moveButtonLabel,
  onMove: browserConfig.moveUrl ? moveCurrentLightboxEventToGallery : null,
});

function filenameFromEvent(event) {
  return event.snapshot_url.split("/").pop() || "motion-event.jpg";
}

function formatPhotoCount(count) {
  return `${count} photo${count === 1 ? "" : "s"}`;
}

function createEventLightbox({ moveButtonLabel, onMove }) {
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
  if (onMove) {
    controls.append(moveButton);
  }
  controls.append(closeButton);
  dialog.append(controls, image, caption);
  overlay.append(dialog);
  document.body.append(overlay);

  let items = [];
  let currentIndex = 0;

  function currentItem() {
    return items[currentIndex] || null;
  }

  function showIndex(index) {
    if (!items.length) {
      return;
    }
    currentIndex = (index + items.length) % items.length;
    const event = currentItem();
    image.src = `${event.snapshot_url}?t=${Date.now()}`;
    image.alt = `Saved photo ${event.detected_at}`;
    caption.textContent = `${new Date(event.detected_at).toLocaleString()} - ${filenameFromEvent(event)}`;
  }

  function close() {
    overlay.classList.add("hidden");
    image.removeAttribute("src");
    document.body.classList.remove("lightbox-open");
  }

  function open(nextItems, startIndex) {
    items = nextItems;
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
  if (onMove) {
    moveButton.addEventListener("click", async () => {
      const event = currentItem();
      if (!event) {
        return;
      }
      moveButton.disabled = true;
      try {
        await onMove(event, { close });
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

  return { open };
}

function updateBrowserActionButtons() {
  const totalEvents = browserEvents.length;
  const selectedCount = selectedBrowserFilenames.size;
  const hasEvents = totalEvents > 0;
  const hasSelection = selectedCount > 0;

  browserSelectButton.disabled = !hasEvents;
  browserDownloadButton.disabled = !hasSelection;
  browserDeleteButton.disabled = !hasSelection;
  browserSelectButton.textContent =
    hasEvents && selectedCount === totalEvents ? "Clear Selection" : "Select All";
}

function renderBrowserEvents(events) {
  browserEvents = events;
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

  for (const [index, event] of events.entries()) {
    const filename = filenameFromEvent(event);
    const card = document.createElement("article");
    card.className = "event-card";

    const imageLink = document.createElement("a");
    imageLink.className = "event-image-link";
    imageLink.href = event.snapshot_url;
    imageLink.title = "Open full image";
    imageLink.addEventListener("click", (clickEvent) => {
      clickEvent.preventDefault();
      browserLightbox.open(browserEvents, index);
    });

    const img = document.createElement("img");
    img.src = `${event.snapshot_url}?max_w=480&max_h=360&quality=70&t=${Date.now()}`;
    img.alt = `Saved photo ${event.detected_at}`;
    img.loading = "lazy";
    imageLink.append(img);

    const body = document.createElement("div");
    body.className = "event-card-body";

    const selection = document.createElement("label");
    selection.className = "event-select";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedBrowserFilenames.has(filename);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedBrowserFilenames.add(filename);
      } else {
        selectedBrowserFilenames.delete(filename);
      }
      updateBrowserActionButtons();
    });

    const selectionLabel = document.createElement("span");
    selectionLabel.textContent = "Select";
    selection.append(checkbox, selectionLabel);

    const title = document.createElement("h3");
    title.textContent = new Date(event.detected_at).toLocaleString();

    const path = document.createElement("p");
    path.className = "subtle";
    path.textContent = filename;

    const actions = document.createElement("div");
    actions.className = "event-card-actions";

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
    body.append(selection, title, path, actions);
    card.append(imageLink, body);
    browserEventList.append(card);
  }

  updateBrowserActionButtons();
}

async function refreshBrowserEvents() {
  const response = await fetch(browserConfig.listUrl);
  const payload = await response.json();
  if (!response.ok) {
    browserMessage.textContent = payload.error || browserConfig.refreshErrorMessage;
    return;
  }

  renderBrowserEvents(payload.events || []);
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
    body: JSON.stringify({ filenames }),
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

  for (const filename of filenames) {
    selectedBrowserFilenames.delete(filename);
  }
  renderBrowserEvents(payload.events || payload.gallery || []);
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
    body: JSON.stringify({ filenames }),
  });
  const payload = await response.json();

  if (!response.ok) {
    browserMessage.textContent = payload.error || browserConfig.moveErrorMessage;
    return false;
  }

  for (const filename of filenames) {
    selectedBrowserFilenames.delete(filename);
  }
  renderBrowserEvents(payload.events || []);
  browserMessage.textContent = `Moved ${formatPhotoCount(payload.moved_count)} to gallery.`;
  return true;
}

async function moveCurrentLightboxEventToGallery(event, { close }) {
  const filename = filenameFromEvent(event);
  const moved = await moveBrowserEventsToGallery([filename]);
  if (moved) {
    close();
  }
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
  renderBrowserEvents(browserEvents);
});

browserDownloadButton.addEventListener("click", () => {
  void downloadBrowserEvents(Array.from(selectedBrowserFilenames));
});

browserDeleteButton.addEventListener("click", () => {
  void deleteBrowserEvents(Array.from(selectedBrowserFilenames));
});

renderBrowserEvents(initialEvents);
window.setInterval(() => {
  void refreshBrowserEvents();
}, 15000);
