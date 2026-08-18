export default function ThisWeekSidebar() {
  return (
    <aside className="this-week">
      <div className="this-week-header">
        <span className="this-week-title">THIS WEEK</span>
        <span className="illustrative-note">Illustrative — not live data</span>
      </div>

      <div className="this-week-item">
        <span className="this-week-tag">ALL ROUNDS</span>
        <div className="this-week-item-headline">Scores update after movie night</div>
        <div className="this-week-item-body">Ratings and financials are entered manually after each round wraps.</div>
      </div>

      <div className="this-week-item">
        <span className="this-week-tag">ALL OWNERS</span>
        <div className="this-week-item-headline">New picks lock each cycle</div>
        <div className="this-week-item-body">Once a round's movie is set, it can't be changed.</div>
      </div>
    </aside>
  )
}
