import PlayerCard from './PlayerCard.jsx'

export default function Leaderboard({ rows, onWatchChange }) {
  // Every player is a possible viewer of every film, so the full roster goes down the tree.
  const owners = rows.map((r) => r.owner)
  return (
    <div className="leaderboard">
      {rows.map((row) => (
        <PlayerCard
          key={row.owner}
          summary={row}
          ownerCount={rows.length}
          owners={owners}
          onWatchChange={onWatchChange}
        />
      ))}
    </div>
  )
}
