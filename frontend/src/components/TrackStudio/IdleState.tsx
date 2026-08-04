/**
 * IdleState — Empty-state illustration when no tracks or history exist.
 */

export function IdleState() {
  return (
    <div className="text-center py-12 text-[#777777]">
      <p className="text-4xl mb-3">🎧</p>
      <p className="text-sm">Select a workflow path and click Generate to start</p>
      <div className="mt-4 grid grid-cols-3 gap-4 text-xs max-w-lg mx-auto">
        <div className="p-3 rounded-lg bg-[#1f1f1f]/50 border border-[#2a2a38]">
          <p className="text-[#b0b0b0] font-medium">Path A</p>
          <p className="text-[#777777] mt-1">Type a prompt, get music</p>
        </div>
        <div className="p-3 rounded-lg bg-[#1f1f1f]/50 border border-[#2a2a38]">
          <p className="text-[#b0b0b0] font-medium">Path B</p>
          <p className="text-[#777777] mt-1">Music + vocals combined</p>
        </div>
        <div className="p-3 rounded-lg bg-[#1f1f1f]/50 border border-[#2a2a38]">
          <p className="text-[#b0b0b0] font-medium">Path C</p>
          <p className="text-[#777777] mt-1">Upload audio, get stems</p>
        </div>
      </div>
    </div>
  );
}
