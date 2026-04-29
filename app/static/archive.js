const initialEvents = JSON.parse(document.getElementById("archive-events").textContent);
const archiveEventList = document.getElementById("archive-event-list");
const archiveMessage = document.getElementById("archive-message");
const archiveSelectButton = document.getElementById("archive-select-button");
const archiveDownloadButton = document.getElementById("archive-download-button");
const archiveDeleteButton = document.getElementById("archive-delete-button");

let archiveEvents = initialEvents;
const selectedArchiveFilenames = new Set();
const archiveLightbox = createEventLightbox();

function createEventLightbox() {
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

  const closeButton = document.createElement("button");
  closeButton.type = "button";
  closeButton.textContent = "Close";

  const image = document.createElement("img");
  image.className = "lightbox-image";
  image.alt = "";

  const caption = document.createElement("p");
  caption.className = "lightbox-caption";

  controls.append(previousButton, nextButton, closeButton);
  dialog.append(controls, image, caption);
  overlay.append(dialog);
  document.body.append(overlay);

  let items = [];
  let currentIndex = 0;

  function showIndex(index) {
    if (!items.length) {
      return;
    }
    currentIndex = (index + items.length) % items.length;
    const event = items[currentIndex];
    const filename = event.snapshot_url.split("/").pop() || "motion-event.jpg";
    image.src = `${event.snapshot_url}?t=${Date.now()}`;
    image.alt = `Motion event ${event.detected_at}`;
    caption.textContent = `${new Date(event.detected_at).toLocaleString()} - ${filename}`;
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

function updateArchiveActionButtons() {
  const totalEvents = archiveEvents.length;
  const selectedCount = selectedArchiveFilenames.size;
  const hasEvents = totalEvents > 0;
  const hasSelection = selectedCount > 0;

  archiveSelectButton.disabled = !hasEvents;
  archiveDownloadButton.disabled = !hasSelection;
  archiveDeleteButton.disabled = !hasSelection;
  archiveSelectButton.textContent =
    hasEvents && selectedCount === totalEvents ? "Clear Selection" : "Select All";
}

function renderArchiveEvents(events) {
  archiveEvents = events;
  const eventFilenames = new Set(
    events.map((event) => event.snapshot_url.split("/").pop()).filter(Boolean),
  );
  for (const filename of Array.from(selectedArchiveFilenames)) {
    if (!eventFilenames.has(filename)) {
      selectedArchiveFilenames.delete(filename);
    }
  }

  archiveEventList.innerHTML = "";
  if (!events.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No saved motion events yet.";
    archiveEventList.append(empty);
    updateArchiveActionButtons();
    return;
  }

  for (const [index, event] of events.entries()) {
    const filename = event.snapshot_url.split("/").pop() || "motion-event.jpg";
    const card = document.createElement("article");
    card.className = "event-card";

    const imageLink = document.createElement("a");
    imageLink.className = "event-image-link";
    imageLink.href = event.snapshot_url;
    imageLink.title = "Open full image";
    imageLink.addEventListener("click", (clickEvent) => {
      clickEvent.preventDefault();
      archiveLightbox.open(archiveEvents, index);
    });

    const img = document.createElement("img");
    img.src = `${event.snapshot_url}?max_w=480&max_h=360&quality=70&t=${Date.now()}`;
    img.alt = `Motion event ${event.detected_at}`;
    img.loading = "lazy";
    imageLink.append(img);

    const body = document.createElement("div");
    body.className = "event-card-body";

    const selection = document.createElement("label");
    selection.className = "event-select";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedArchiveFilenames.has(filename);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedArchiveFilenames.add(filename);
      } else {
        selectedArchiveFilenames.delete(filename);
      }
      updateArchiveActionButtons();
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
      void deleteArchiveEvents([filename]);
    });

    actions.append(download, removeButton);
    body.append(selection, title, path, actions);
    card.append(imageLink, body);
    archiveEventList.append(card);
  }

  updateArchiveActionButtons();
}

async function refreshArchiveEvents() {
  const response = await fetch("/api/events");
  const payload = await response.json();
  if (!response.ok) {
    archiveMessage.textContent = payload.error || "Archive refresh failed.";
    return;
  }

  renderArchiveEvents(payload.events || []);
}

async function downloadArchiveEvents(filenames) {
  if (!filenames.length) {
    archiveMessage.textContent = "Select at least one event image.";
    return;
  }

  archiveMessage.textContent = "Preparing download...";
  const response = await fetch("/api/events/download", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filenames }),
  });

  if (!response.ok) {
    const payload = await response.json();
    archiveMessage.textContent = payload.error || "Download failed.";
    return;
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  const contentDisposition = response.headers.get("Content-Disposition") || "";
  const match = contentDisposition.match(/filename="?([^"]+)"?/);
  link.href = url;
  link.download = match ? match[1] : "motionsense-events.zip";
  document.body.append(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
  archiveMessage.textContent = `Downloaded ${filenames.length} photo${filenames.length === 1 ? "" : "s"}.`;
}

async function deleteArchiveEvents(filenames) {
  if (!filenames.length) {
    archiveMessage.textContent = "Select at least one event image.";
    return;
  }
  if (!window.confirm(`Delete ${filenames.length} photo${filenames.length === 1 ? "" : "s"}?`)) {
    return;
  }

  archiveMessage.textContent = "Deleting event photos...";
  const response = await fetch("/api/events/delete", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ filenames }),
  });
  const payload = await response.json();

  if (!response.ok) {
    archiveMessage.textContent = payload.error || "Delete failed.";
    return;
  }

  for (const filename of filenames) {
    selectedArchiveFilenames.delete(filename);
  }
  renderArchiveEvents(payload.events || []);
  archiveMessage.textContent = `Deleted ${payload.deleted_count} photo${payload.deleted_count === 1 ? "" : "s"}.`;
}

archiveSelectButton.addEventListener("click", () => {
  if (selectedArchiveFilenames.size === archiveEvents.length) {
    selectedArchiveFilenames.clear();
  } else {
    for (const event of archiveEvents) {
      const filename = event.snapshot_url.split("/").pop();
      if (filename) {
        selectedArchiveFilenames.add(filename);
      }
    }
  }
  renderArchiveEvents(archiveEvents);
});

archiveDownloadButton.addEventListener("click", () => {
  void downloadArchiveEvents(Array.from(selectedArchiveFilenames));
});

archiveDeleteButton.addEventListener("click", () => {
  void deleteArchiveEvents(Array.from(selectedArchiveFilenames));
});

renderArchiveEvents(initialEvents);
window.setInterval(() => {
  void refreshArchiveEvents();
}, 15000);
