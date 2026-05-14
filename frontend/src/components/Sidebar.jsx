import React from 'react'

export default function Sidebar({page, setPage}){
  const items = [
    {key: 'overview', label: 'Overview'},
    {key: 'search', label: 'Search for items'},
    {key: 'items', label: 'Add / Edit items'},
    {key: 'containers', label: 'Containers'},
    {key: 'tags', label: 'Tags'},
    {key: 'placements', label: 'Assign items'},
    {key: 'config', label: 'Configuration'},
  ]

  return (
    <aside className="sidebar">
      <div className="brand">
        <strong>whereisit</strong>
      </div>
      <nav>
        {items.map(it => (
          <div key={it.key} className={"sidebar-item" + (page===it.key? ' active':'')} onClick={()=>setPage(it.key)}>
            {it.label}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer small">Profile • Log out</div>
    </aside>
  )
}
