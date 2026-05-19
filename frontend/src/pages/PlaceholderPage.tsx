type PlaceholderPageProps = {
  title: string
  description: string
  status: string
}

function PlaceholderPage({ title, description, status }: PlaceholderPageProps) {
  return (
    <section className="feature-panel" aria-labelledby="feature-title">
      <div>
        <h2 id="feature-title">{title}</h2>
        <p>{description}</p>
      </div>
      <span>{status}</span>
    </section>
  )
}

export default PlaceholderPage
