import React from 'react'
import ReactDOM from 'react-dom/client'
import 'leaflet/dist/leaflet.css'
import './index.css'
import ConsoleApp from './console/ConsoleApp'

// The ASCII console is the site. The original cream/navy survey dashboard is
// still in ./App and still works -- it is mounted at /classic by the console's
// router, so the bento views remain reachable rather than orphaned.
ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ConsoleApp />
  </React.StrictMode>,
)
