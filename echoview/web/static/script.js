/**************************************************************
 * script.js - Consolidated client-side JS for EchoView
 * - Handles fetching stats (CPU/mem/etc.)
 * - Toggles collapsible sections
 * - Mixed folder UI, lazy thumbnails, overlay dragging, etc.
 **************************************************************/

// ---- Global Stats Updater ----
function fetchStats() {
  fetch("/stats")
    .then(r => r.json())
    .then(data => {
      const cpuEl = document.getElementById("stat_cpu");
      const memEl = document.getElementById("stat_mem");
      const loadEl = document.getElementById("stat_load");
      const tempEl = document.getElementById("stat_temp");
      const diskEl = document.getElementById("stat_disk");
      if (cpuEl)  cpuEl.textContent = data.cpu_percent + "%";
      if (memEl)  memEl.textContent = data.mem_used_mb + "MB";
      if (loadEl) loadEl.textContent = data.load_1min;
      if (tempEl) tempEl.textContent = data.temp;
      if (diskEl) diskEl.textContent = data.disk_used + "/" + data.disk_total;
    })
    .catch(e => console.log("Stats fetch error:", e));
}
// Poll stats every 10s
setInterval(fetchStats, 10000);
window.addEventListener("load", fetchStats);

// ---- Collapsible Sections ----
function initCollapsible() {
  const headers = document.querySelectorAll(".collapsible-header");
  headers.forEach(hdr => {
    hdr.addEventListener("click", () => {
      const content = hdr.nextElementSibling;
      if (!content) return;
      content.classList.toggle("open");
    });
  });
}
window.addEventListener("DOMContentLoaded", initCollapsible);

// ---- Mode section toggling ----
function showModeSection(dname, mode) {
  const all = ['random','category','specific_image','mixed','videos','spotify','web_page'];
  const map = {
    'random_image': ['random','category'],
    'specific_image': ['category','specific_image'],
    'mixed': ['random','mixed'],
    'videos': ['videos'],
    'spotify': ['spotify'],
    'web_page': ['web_page']
  };
  const toShow = map[mode] || [];
  all.forEach(sec => {
    const el = document.getElementById(`${dname}_${sec}_section`);
    if (el) el.style.display = toShow.includes(sec) ? 'block' : 'none';
  });
  if (mode === 'mixed') {
    const sec = document.getElementById(`${dname}_mixed_section`);
    if (sec && !sec.dataset.init) {
      initMixedUI(dname);
      sec.dataset.init = '1';
    }
  }
}

function initModeHandlers() {
  document.querySelectorAll('select[id$="_mode"]').forEach(sel => {
    const dname = sel.id.replace('_mode','');
    sel.addEventListener('change', () => {
      showModeSection(dname, sel.value);
    });
    showModeSection(dname, sel.value);
  });
}
document.addEventListener('DOMContentLoaded', initModeHandlers);

// ---- Mixed Folder UI (click to move items) ----
function initMixedUI(dispName) {
  const searchBox = document.getElementById(dispName + "_search");
  const availList = document.getElementById(dispName + "_availList");
  const selList = document.getElementById(dispName + "_selList");
  const hiddenOrder = document.getElementById(dispName + "_mixed_order");
  if (!availList || !selList) return;

  function sortAvailable() {
    const items = Array.from(availList.querySelectorAll("li"));
    items.sort((a, b) => {
      let fa = a.getAttribute("data-folder").toLowerCase();
      let fb = b.getAttribute("data-folder").toLowerCase();
      return fa.localeCompare(fb);
    });
    items.forEach(li => availList.appendChild(li));
  }

  if (searchBox) {
    searchBox.addEventListener("input", () => {
      const txt = searchBox.value.toLowerCase();
      const items = availList.querySelectorAll("li");
      items.forEach(li => {
        const folder = li.getAttribute("data-folder").toLowerCase();
        li.style.display = folder.includes(txt) ? "" : "none";
      });
    });
  }

  let dragSrcEl = null;
  function handleDragStart(e) {
    dragSrcEl = this;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/html", this.innerHTML);
  }
  function handleDragOver(e) {
    if (e.preventDefault) e.preventDefault();
    return false;
  }
  function handleDragEnter(e) {
    this.classList.add("selected");
  }
  function handleDragLeave(e) {
    this.classList.remove("selected");
  }
  function handleDrop(e) {
    if (e.stopPropagation) e.stopPropagation();
    if (dragSrcEl != this) {
      const oldHTML = dragSrcEl.innerHTML;
      dragSrcEl.innerHTML = this.innerHTML;
      this.innerHTML = e.dataTransfer.getData("text/html");
    }
    return false;
  }
  function handleDragEnd(e) {
    const items = selList.querySelectorAll("li");
    items.forEach(li => li.classList.remove("selected"));
    updateHiddenOrder();
  }
  function addDnDHandlers(item) {
    item.addEventListener("dragstart", handleDragStart);
    item.addEventListener("dragenter", handleDragEnter);
    item.addEventListener("dragover", handleDragOver);
    item.addEventListener("dragleave", handleDragLeave);
    item.addEventListener("drop", handleDrop);
    item.addEventListener("dragend", handleDragEnd);
  }

  function moveItem(li, sourceUL, targetUL) {
    targetUL.appendChild(li);
    if (targetUL === selList) {
      addDnDHandlers(li);
    } else {
      sortAvailable();
    }
    updateHiddenOrder();
  }

  availList.addEventListener("click", e => {
    if (e.target.tagName === "LI") {
      moveItem(e.target, availList, selList);
    }
  });
  selList.addEventListener("click", e => {
    if (e.target.tagName === "LI") {
      moveItem(e.target, selList, availList);
    }
  });

  function updateHiddenOrder() {
    const items = selList.querySelectorAll("li");
    const arr = [];
    items.forEach(li => arr.push(li.getAttribute("data-folder")));
    hiddenOrder.value = arr.join(",");
  }

  // Initialize
  const selItems = selList.querySelectorAll("li");
  selItems.forEach(li => addDnDHandlers(li));
  sortAvailable();
}

// ---- Video play-to-end toggle ----
function initVideoPlayToEndToggle() {
  const checkboxes = document.querySelectorAll('.video-play-to-end');
  checkboxes.forEach(cb => {
    const prefix = cb.id.replace('_video_play_to_end', '');
    const container = document.getElementById(prefix + '_max_seconds_container');
    const toggle = () => {
      if (!container) return;
      container.style.display = cb.checked ? 'none' : 'block';
    };
    cb.addEventListener('change', toggle);
    toggle();
  });
}
window.addEventListener('DOMContentLoaded', initVideoPlayToEndToggle);

// ---- Video mute toggle ----
function initVideoMuteToggle() {
  const checkboxes = document.querySelectorAll('.video-mute');
  checkboxes.forEach(cb => {
    const prefix = cb.id.replace('_video_mute', '');
    const container = document.getElementById(prefix + '_volume_container');
    const toggle = () => {
      if (!container) return;
      container.style.display = cb.checked ? 'none' : 'block';
    };
    cb.addEventListener('change', toggle);
    toggle();
  });
}
window.addEventListener('DOMContentLoaded', initVideoMuteToggle);

// ---- Lazy load thumbnails for specific_image mode ----
function loadSpecificThumbnails(dispName) {
  const container = document.getElementById(dispName + "_lazyContainer");
  if (!container) return;
  const allThumbs = JSON.parse(container.getAttribute("data-files") || "[]");
  const shownCount = container.querySelectorAll("label.thumb-label").length;
  const nextLimit = shownCount + 100;

  const slice = allThumbs.slice(shownCount, nextLimit);
  slice.forEach(filePath => {
    const bn = filePath.split("/").pop();
    const lbl = document.createElement("label");
    lbl.className = "thumb-label";
    const img = document.createElement("img");
    img.src = "/thumb/" + filePath + "?size=60";
    img.loading = "lazy";
    img.style.width = "60px";
    img.style.height = "60px";
    img.style.objectFit = "cover";
    img.style.border = "2px solid #555";
    img.style.borderRadius = "4px";
    img.style.margin = "5px";
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = dispName + "_specific_image";
    radio.value = bn;

    lbl.appendChild(img);
    lbl.appendChild(document.createElement("br"));
    lbl.appendChild(radio);
    lbl.appendChild(document.createTextNode(" " + bn));
    container.insertBefore(lbl, container.lastElementChild);
  });

  if (nextLimit >= allThumbs.length && container.lastElementChild) {
    container.lastElementChild.style.display = "none";
  }
}

// ---- Overlay Dragging (for overlay.html) ----
function initOverlayDragUI() {
  const previewBox = document.getElementById("overlayPreviewBox");
  const dragBox = document.getElementById("overlayDraggable");
  if (!previewBox || !dragBox) return;

  const xInput = document.getElementById("offset_x");
  const yInput = document.getElementById("offset_y");

  // Use scaleFactor provided from server; default to 1 if not set.
  if (typeof scaleFactor === "undefined") {
    scaleFactor = 1.0;
  }

  dragBox.addEventListener("mousedown", (e) => {
    e.preventDefault();
    isDragging = true;
    startMouseX = e.clientX;
    startMouseY = e.clientY;
    dragOffsetX = parseFloat(dragBox.style.left || "0");
    dragOffsetY = parseFloat(dragBox.style.top || "0");
  });

  document.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    e.preventDefault();
    const dx = e.clientX - startMouseX;
    const dy = e.clientY - startMouseY;
    let newLeft = dragOffsetX + dx;
    let newTop = dragOffsetY + dy;

    const maxLeft = previewBox.clientWidth - dragBox.clientWidth;
    const maxTop = previewBox.clientHeight - dragBox.clientHeight;

    if (newLeft < -dragBox.clientWidth + 10) newLeft = -dragBox.clientWidth + 10;
    if (newTop < -dragBox.clientHeight + 10) newTop = -dragBox.clientHeight + 10;
    if (newLeft > (maxLeft + dragBox.clientWidth) - 10)
      newLeft = (maxLeft + dragBox.clientWidth) - 10;
    if (newTop > (maxTop + dragBox.clientHeight) - 10)
      newTop = (maxTop + dragBox.clientHeight) - 10;

    dragBox.style.left = newLeft + "px";
    dragBox.style.top = newTop + "px";
    if (xInput && yInput) {
      xInput.value = Math.round(newLeft / scaleFactor);
      yInput.value = Math.round(newTop / scaleFactor);
    }
  });

  document.addEventListener("mouseup", (e) => {
    isDragging = false;
  });
}
let isDragging = false, dragOffsetX = 0, dragOffsetY = 0, startMouseX = 0, startMouseY = 0;
window.addEventListener("DOMContentLoaded", initOverlayDragUI);

// A helper to auto-submit the overlay form on monitor change
function onMonitorChange() {
  const selForm = document.getElementById("monitorSelectForm");
  if (selForm) selForm.submit();
}

// Mobile sidebar toggle
window.addEventListener('DOMContentLoaded', () => {
  const navToggle = document.getElementById('nav-toggle');
  const sidebar = document.querySelector('.sidebar');
  if (navToggle && sidebar) {
    navToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
  }
});

// Toggle per-file action menus in media manager
function toggleFileMenu(btn) {
  const item = btn.closest('.file-item');
  if (item) {
    item.classList.toggle('open');
  }
}

// Close any open file menus when clicking outside
document.addEventListener('click', (e) => {
  if (!e.target.closest('.file-item')) {
    document.querySelectorAll('#file-manager .file-item.open').forEach(el => {
      el.classList.remove('open');
    });
  }
});
