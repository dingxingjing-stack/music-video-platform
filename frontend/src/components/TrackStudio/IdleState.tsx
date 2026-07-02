/**
 * IdleState — Empty-state illustration when no tracks or history exist.
 */

export function IdleState() {
  return (
    <div className="text-center py-12 text-gray-600">
      <p className="text-4xl mb-3">🎧</p>
      <p className="text-sm">Select a workflow path and click Generate to start</p>
      <div className="mt-4 grid grid-cols-3 gap-4 text-xs max-w-lg mx-auto">
        <div className="p-3 rounded-lg bg-gray-900/50 border border-gray-800">
          <p className="text-gray-400 font-medium">Path A</p>
          <p className="text-gray-600 mt-1">Type a prompt, get music</p>
        </div>
        <div className="p-3 rounded-lg bg-gray-900/50 border border-gray-800">
          <p className="text-gray-400 font-medium">Path B</p>
          <p className="text-gray-600 mt-1">Music + vocals combined</p>
        </div>
        <div className="p-3 rounded-lg bg-gray-900/50 border border-gray-800">
          <p className="text-gray-400 font-medium">Path C</p>
          <p className="text-gray-600 mt-1">Upload audio, get stems</p>
        </div>
      </div>
    </div>
  );
}
