import React from 'react';
import {AbsoluteFill, Composition, Img, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import actions from './actions.json';
import config from './render-config.json';

type Props = {action: number};

export const Action = ({action}: Props) => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{backgroundColor: '#00ff00'}}>
    <Img src={staticFile(`${config.preparedFolder}/${actions[action].id}/${String(frame).padStart(3, '0')}.png`)}
      style={{position: 'absolute', width: 320, height: 320, left: 160, top: 16}} />
  </AbsoluteFill>;
};

const Root = () => <>
  {actions.map((item, action) => <Composition key={item.id} id={item.id} component={Action}
    width={config.width} height={config.height} fps={config.fps}
    durationInFrames={config.fps * config.durationSeconds} defaultProps={{action}} />)}
</>;
registerRoot(Root);
