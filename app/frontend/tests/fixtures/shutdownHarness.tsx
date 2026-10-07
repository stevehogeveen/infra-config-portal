import React from 'react';
import {createRoot} from 'react-dom/client';
import {ShutdownForReset} from '../../src/components/ShutdownForReset';
import '../../src/workflow.css';

createRoot(document.getElementById('root')!).render(<ShutdownForReset profileId="fixture" deviceId="fixture" disabled={false} onBusy={()=>{}}/>);
