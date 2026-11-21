import React from 'react';
import {AbsoluteFill, Composition, Img, registerRoot, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import actions from './actions.json';
import safeActions from './safe-actions.json';

type Props = {action: number};

export const Action = ({action}: Props) => {
  const frame = useCurrentFrame();
  const folder = safeActions.includes(actions[action].id) ? 'frames-safe'
    : actions[action].name === '睡觉-循环' ? 'frames-v3' : action >= 99 ? 'frames-v2' : 'frames';
  return <AbsoluteFill style={{backgroundColor: '#00ff00'}}>
    <Img src={staticFile(`${folder}/${actions[action].id}/${String(frame).padStart(3, '0')}.png`)}
      style={{position: 'absolute', width: 320, height: 320, left: 160, top: 16}} />
  </AbsoluteFill>;
};

const Root = () => <>
  {actions.map((item, action) => <Composition key={item.id} id={item.id} component={Action}
    width={640} height={360} fps={30} durationInFrames={300} defaultProps={{action}} />)}
</>;
registerRoot(Root);
