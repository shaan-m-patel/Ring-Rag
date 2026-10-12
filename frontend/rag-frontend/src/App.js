// src/App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import Upload from './pages/Upload';
import Queries from './pages/Queries';
import Visualization from './pages/Visualization';
import Footer from './components/Footer';
import ApiTokenField from './components/ApiTokenField';

import './index.css'; // or App.css where you put the styles

function App() {
  return (
    <Router>
      <div className="App">
        {/* Main content area */}
        <div className="content">
          <ApiTokenField />
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/queries" element={<Queries />} />
            <Route path="/visualization" element={<Visualization />} />
          </Routes>
        </div>

        {/* Sticky footer at the bottom */}
        <Footer />
      </div>
    </Router>
  );
}

export default App;
