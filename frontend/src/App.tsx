import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { Navbar } from './components/layout/Navbar';
import { AppRouter } from './app/router';

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100 selection:bg-cyan-500/30 selection:text-cyan-200">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 py-8">
          <AppRouter />
        </main>
        <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-600">
          ORCA Open-Source Marine & Coastal Intelligence Platform • Verified Multi-Agent System
        </footer>
      </div>
    </BrowserRouter>
  );
}

export default App;
