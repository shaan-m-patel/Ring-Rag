// src/pages/Upload.js
import React, { useState } from 'react';
import { apiFetch, readApiPayload } from '../api';

function Upload() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedFolder, setSelectedFolder] = useState([]);
  const [url, setUrl] = useState('');
  const [status, setStatus] = useState('');

  const handleFileSelect = (e) => {
    setSelectedFile(e.target.files[0]);
  };

  const handleFolderSelect = (e) => {
    // This is an array of files if the user selected a folder with webkitdirectory
    setSelectedFolder(e.target.files);
  };

  const handleUrlChange = (e) => {
    setUrl(e.target.value);
  };

  const handleFileUpload = async () => {
    if (!selectedFile) {
      console.log('No file selected.');
      return;
    }
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);

      const response = await apiFetch('/upload_file', {
        method: 'POST',
        body: formData,
      });

      const data = await readApiPayload(response);
      if (!response.ok) {
        setStatus(data.error || 'File upload failed.');
        console.error('Error uploading file:', data.error || data);
      } else {
        setStatus(data.message || 'File upload success.');
        console.log('File upload success:', data.message);
      }
    } catch (error) {
      setStatus('Upload failed.');
      console.error('Upload failed:', error);
    }
  };

  const handleFolderUpload = async () => {
    if (!selectedFolder || selectedFolder.length === 0) {
      console.log('No folder files selected.');
      return;
    }
    try {
      const formData = new FormData();
      // Append each file under the same form field name "files"
      for (let i = 0; i < selectedFolder.length; i++) {
        formData.append('files', selectedFolder[i]);
      }

      const response = await apiFetch('/upload_folder', {
        method: 'POST',
        body: formData,
      });

      const data = await readApiPayload(response);
      if (!response.ok) {
        setStatus(data.error || 'Folder upload failed.');
        console.error('Error uploading folder:', data.error || data);
      } else {
        setStatus(data.message || 'Folder upload success.');
        console.log('Folder upload success:', data.message);
        console.log('Files:', data.files);
      }
    } catch (error) {
      setStatus('Folder upload failed.');
      console.error('Folder upload failed:', error);
    }
  };

  const handleUrlProcess = async () => {
    if (!url) {
      console.log('No URL specified.');
      return;
    }
    try {
      const response = await apiFetch('/process_url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });

      const data = await readApiPayload(response);
      if (!response.ok) {
        setStatus(data.error || 'URL processing failed.');
        console.error('Error processing URL:', data.error || data);
      } else {
        setStatus(data.message || 'URL accepted.');
        console.log('URL processed successfully:', data.message);
      }
    } catch (error) {
      setStatus('URL processing failed.');
      console.error('URL processing failed:', error);
    }
  };

  return (
    <div style={styles.container}>
      <h2>Upload Page</h2>
      {status && <p>{status}</p>}

      {/* Document Upload */}
      <div style={styles.section}>
        <h3>Document Upload</h3>
        <input type="file" onChange={handleFileSelect} />
        <button onClick={handleFileUpload}>Upload Document</button>
      </div>

      {/* Folder Upload */}
      <div style={styles.section}>
        <h3>Folder Upload</h3>
        <input
          type="file"
          webkitdirectory="true"
          directory="true"
          multiple
          onChange={handleFolderSelect}
        />
        <button onClick={handleFolderUpload}>Upload Folder</button>
      </div>

      {/* Website URL Input */}
      <div style={styles.section}>
        <h3>Website URL</h3>
        <input
          type="text"
          value={url}
          onChange={handleUrlChange}
          placeholder="Enter website URL"
        />
        <button onClick={handleUrlProcess}>Process URL</button>
      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: '1rem',
    backgroundColor: '#f0ffe0', // example background
    minHeight: '90vh',
  },
  section: {
    margin: '1rem 0',
  },
};

export default Upload;
