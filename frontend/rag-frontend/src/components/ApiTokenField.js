import React, { useState } from 'react';
import { getApiToken, setApiToken } from '../api';

function ApiTokenField() {
  const [token, setToken] = useState(getApiToken);
  const [saved, setSaved] = useState(Boolean(getApiToken()));

  const handleSave = () => {
    setApiToken(token);
    setSaved(Boolean(token.trim()));
  };

  return (
    <form
      style={styles.bar}
      onSubmit={(event) => {
        event.preventDefault();
        handleSave();
      }}
    >
      <label htmlFor="api-token">API token</label>
      <input
        id="api-token"
        type="password"
        autoComplete="off"
        value={token}
        placeholder="Token issued for your user"
        onChange={(event) => {
          setToken(event.target.value);
          setSaved(false);
        }}
        style={styles.input}
      />
      <button type="submit">Save token</button>
      <span style={styles.hint}>
        {saved
          ? 'Token saved in this browser. The server checks it on every request.'
          : 'Save a token before querying or uploading. The server rejects requests without one.'}
      </span>
    </form>
  );
}

const styles = {
  bar: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '0.75rem',
    alignItems: 'center',
    marginBottom: '1.5rem',
  },
  input: {
    minWidth: '16rem',
    flex: '1',
  },
  hint: {
    flexBasis: '100%',
    color: '#264653',
  },
};

export default ApiTokenField;
