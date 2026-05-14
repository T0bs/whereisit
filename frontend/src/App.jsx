import React, { useEffect, useState } from 'react'
import Items from './components/Items'
import Containers from './components/Containers'
import Placements from './components/Placements'
import Search from './components/Search'
import Overview from './components/Overview'
import OverviewPage from './pages/OverviewPage'
import ContainerEdit from './components/ContainerEdit'
import ItemEdit from './components/ItemEdit'
import Sidebar from './components/Sidebar'
import Tags from './components/Tags'

function ConfigPage(){
  return (
    <div className="card">
      <h3>Configuration</h3>
      <div className="small">App-level settings go here.</div>
    </div>
  )
}

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export default function App() {
  const [items, setItems] = useState([])
  const [containers, setContainers] = useState([])
  const [theme, setTheme] = useState(() => localStorage.getItem('whereisit:theme') || 'dark')

  const reload = async () => {
    const [ri, rc] = await Promise.all([
      fetch(`${API}/items/`).then(r => r.json()),
      fetch(`${API}/containers/`).then(r => r.json()),
    ])
    setItems(ri)
    setContainers(rc)
  }

  useEffect(() => { reload() }, [])

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
    localStorage.setItem('whereisit:theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  const [page, setPage] = useState('overview')
  const [selectedContainerId, setSelectedContainerId] = useState(null)
  const [selectedItemId, setSelectedItemId] = useState(null)

  const renderPage = () => {
    switch(page){
      case 'overview': return <OverviewPage api={API} onEdit={(type,id)=>{ if(type==='containers') { setSelectedContainerId(id); setSelectedItemId(null) } if(type==='items'){ setSelectedItemId(id); setSelectedContainerId(null) } }} />
      case 'search': return <Search api={API} onSelect={reload} />
      case 'items': return <Items api={API} items={items} onChange={reload} />
      case 'tags': return <Tags api={API} onChange={reload} />
      case 'containers': return <Containers api={API} containers={containers} onChange={reload} />
      case 'placements': return <Placements api={API} items={items} containers={containers} onChange={reload} />
      case 'config': return <ConfigPage />
      default: return <Search api={API} onSelect={reload} />
    }
  }

  return (
    <div className="app">
      <header>
        <h1>Whereisit</h1>
        <div>
          <button className="theme-toggle" onClick={toggleTheme}>{theme === 'dark' ? 'Light' : 'Dark'} mode</button>
        </div>
      </header>

      <div className="layout">
        <Sidebar page={page} setPage={setPage} />
        <section className="content">
          <div className="content-main">
            {renderPage()}
          </div>
        </section>
        <aside className="content-side">
          {selectedContainerId ? (
            <ContainerEdit api={API} containerId={selectedContainerId} onSaved={()=>{ setSelectedContainerId(null); reload() }} onCancel={()=>setSelectedContainerId(null)} />
          ) : selectedItemId ? (
            <ItemEdit api={API} itemId={selectedItemId} onSaved={()=>{ setSelectedItemId(null); reload() }} onCancel={()=>setSelectedItemId(null)} />
          ) : (
            null
          )}
        </aside>
      </div>
    </div>
  )
}
