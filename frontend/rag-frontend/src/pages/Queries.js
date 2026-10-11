// src/pages/Queries.js
import React, { useState } from 'react';
import { apiFetch, readApiPayload } from '../api';

function Queries() {
  const [query, setQuery] = useState('');
  const [currentStep, setCurrentStep] = useState('Idle');
  const [result, setResult] = useState('');

  const handleQueryChange = (e) => {
    setQuery(e.target.value);
  };

  const handleSearch = async () => {
    // Show initial step
    setCurrentStep('Sending query to backend...');
    setResult('');

    try {
      const response = await apiFetch('/query', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query_text: query }),
      });
      const data = await readApiPayload(response);

      if (!response.ok) {
        if (response.status === 401) {
          setCurrentStep('Authentication required');
        } else if (response.status === 429) {
          setCurrentStep('Quota exceeded');
        } else {
          setCurrentStep('Error');
        }
        setResult(data.error || 'Request failed.');
        return;
      }

      setResult(data.answer || 'No answer returned.');
      setCurrentStep('Complete');
    } catch (error) {
      console.error('Error during query:', error);
      setCurrentStep('Error');
      setResult('Something went wrong.');
    }
  };

  return (
    <div style={styles.container}>
      <h2>User Queries</h2>
      <div style={styles.queryContainer}>
        <input
          type="text"
          placeholder="Enter your query..."
          value={query}
          onChange={handleQueryChange}
          style={styles.queryInput}
        />
        <button onClick={handleSearch}>Search</button>
      </div>

      <div style={styles.statusContainer}>
        <h4>Current Step: {currentStep}</h4>
      </div>

      <div style={styles.resultContainer}>
        {result && <p>Final Result: {result}</p>}
      </div>
    </div>
  );
}

const styles = {
  container: {
    padding: '1rem',
  },
  queryContainer: {
    display: 'flex',
    gap: '1rem',
    marginBottom: '1rem',
  },
  queryInput: {
    flex: '1',
  },
  statusContainer: {
    margin: '1rem 0',
  },
  resultContainer: {
    margin: '1rem 0',
  },
};

export default Queries;
