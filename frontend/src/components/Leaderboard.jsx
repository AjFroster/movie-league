import PlayerCard from './PlayerCard.jsx'

export default function Leaderboard({ rows }) {
  return (
    <div className="leaderboard">
      {rows.map((row) => (
        <PlayerCard key={row.owner} summary={row} ownerCount={rows.length} />
      ))}
    </div>
  )
}
