/**
 * PathSelector — Four-path workflow selector with routing.
 * Cards navigate to dedicated pages instead of in-page expand.
 */

import { useNavigate } from 'react-router-dom';
import { PATHS } from '../../types/trackStudio';
import { PathEditor } from '../high-end/PathEditor';

interface Props {
  selectedPath: 'a' | 'b' | 'c' | 'd';
  running: boolean;
  onSelectPath: (path: 'a' | 'b' | 'c' | 'd') => void;
}

export function PathSelector({
  selectedPath,
  running,
  onSelectPath,
}: Props) {
  const navigate = useNavigate();

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {PATHS.map((p) => (
        <PathEditor
          key={p.id}
          pathId={p.id}
          icon={p.icon}
          selected={selectedPath === p.id}
          disabled={running}
          onSelect={(id) => {
            if (id === 'a' || id === 'b' || id === 'c' || id === 'd') {
              onSelectPath(id);
              navigate(`/path-${id}`);
            }
          }}
        />
      ))}
    </div>
  );
}