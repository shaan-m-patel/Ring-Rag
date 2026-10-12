// src/pages/Visualization.js
import React from 'react';
import EmbeddingsChart from '../components/EmbeddingChart';

function Visualization() {
  // Example ingested files
  const ingestedFiles = [
    { id: 1, name: 'document1.pdf', size: '1.2 MB' },
    { id: 2, name: 'document2.docx', size: '800 KB' },
    { id: 3, name: 'website_data.html', size: '300 KB' }
  ];

  return (
    <div style={styles.container}>
      <h2>Data Visualization</h2>

      {/* Example chart for embeddings */}
      <div style={styles.chartSection}>
        <h3>Embeddings Graph</h3>
        <EmbeddingsChart />
      </div>

      {/* Ingested files list */}
      <div style={styles.filesSection}>
        <h3>Ingested Files</h3>
        <table style={styles.table}>
          <thead>
            <tr>
              <th>ID</th>
              <th>File Name</th>
              <th>Size</th>
            </tr>
          </thead>
          <tbody>
            {ingestedFiles.map((file) => (
              <tr key={file.id}>
                <td>{file.id}</td>
                <td>{file.name}</td>
                <td>{file.size}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: '1rem'
  },
  chartSection: {
    marginBottom: '2rem'
  },
  filesSection: {
    marginTop: '2rem'
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse'
  }
};

export default Visualization;
