// upload.js - handles upload form

document.addEventListener('DOMContentLoaded', function() {
  const form = document.getElementById('uploadForm');
  if (!form) return;
  form.onsubmit = function(e) {
    e.preventDefault();
    let fd = new FormData(this);
    fetch('/upload', {method:'POST', body:fd})
      .then(r=>r.json())
      .then(data=>{
        document.getElementById('upload-status').innerHTML = `<span style='color:limegreen;'>Uploaded: ${data.filename}</span>`;
        this.reset();
      })
      .catch(()=>{
        document.getElementById('upload-status').innerHTML = `<span style='color:red;'>Upload failed.</span>`;
      });
  };
});
