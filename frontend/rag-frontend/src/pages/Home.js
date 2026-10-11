// src/pages/Home.js
import React from 'react';
import { Link } from 'react-router-dom';
import RRlogo from '../RRlogo.webp';

function Home() {
  return (
    <div style={{ textAlign: 'center' }}>
      <h1>Prototype Stage 2 RAG</h1>
      <img src={RRlogo} alt="RR Logo" className="rr-logo" />
      <div className="home-buttons">
        <Link to="/upload">
          <button>Upload</button>
        </Link>
        <Link to="/queries">
          <button>User Queries</button>
        </Link>
        <Link to="/visualization">
          <button>Data Visualization</button>
        </Link>
      </div>
    </div>
  );
}

export default Home;
