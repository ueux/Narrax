import HealthCheck from "@/components/health-check";

export default function Home() {
  return (
    <main className="container">
      <h1>NarraX</h1>
      <p className="subtitle">Real-Time Narrative Intelligence Engine</p>
      <p>
        Discover what people are actually believing and saying about a topic — and how
        those narratives change.
      </p>
      <HealthCheck />
    </main>
  );
}
