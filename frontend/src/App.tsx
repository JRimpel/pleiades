import StargazingMap from './components/StargazingMap'
import './App.css'

function App() {
  return (
    <main className="app">
      <header className="app-header">
        <div>
          <h1>Pleiades</h1>
          <p>Find your next constellation lookout in Western New York</p>
        </div>
        <span className="region-label">Western New York</span>
      </header>
      <StargazingMap />
    </main>
  )
}

export default App
