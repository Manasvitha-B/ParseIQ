import Navbar from './components/Navbar'
import Hero from './components/Hero'
import TransformationSection from './components/TransformationSection'
import DocumentAnatomy from './components/DocumentAnatomy'
import Pipeline from './components/Pipeline'
import Architecture from './components/Architecture'
import ParserDemo from './components/ParserDemo'
import ConfidencePanel from './components/ConfidencePanel'
import FailureHandling from './components/FailureHandling'
import FinalCTA from './components/FinalCTA'
import Footer from './components/Footer'
import './App.css'

export default function App() {
  return (
    <div className="app">
      <Navbar />
      <main>
        <Hero />
        <TransformationSection />
        <DocumentAnatomy />
        <Pipeline />
        <Architecture />
        <ParserDemo />
        <ConfidencePanel />
        <FailureHandling />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  )
}
