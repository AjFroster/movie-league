import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { AuthProvider } from './auth.jsx'
import './styles.css'

// AuthProvider owns the ClerkProvider, because it also has to handle the case where there
// is no Clerk at all. `clerk init` tried to add a second one here, nested inside this one
// and with no publishableKey -- two providers, the inner one blank.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>
)
