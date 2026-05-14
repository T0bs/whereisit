import React from 'react'

export default function DetailModal({ open, onClose, title, data }){
  if(!open) return null
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={e=>e.stopPropagation()}>
        <div className="modal-header">
          <h3>{title}</h3>
          <button className="small" onClick={onClose}>Close</button>
        </div>
        <div className="modal-body">
          {data ? (
            <table className="detail-table">
              <tbody>
                {Object.keys(data).map(k => (
                  <tr key={k}><th>{k}</th><td>{String(data[k])}</td></tr>
                ))}
              </tbody>
            </table>
          ) : <div className="small">Loading...</div>}
        </div>
      </div>
    </div>
  )
}
