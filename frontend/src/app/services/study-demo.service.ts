import { Injectable } from '@angular/core';
import { Material, ToolId, ToolResult } from '../models/material';

export const MATERIAL_TOOLS:readonly {id:ToolId;title:string;description:string}[]=[
  {id:'summary',title:'Summary',description:'Condense this file into the key ideas.'},
  {id:'flashcards',title:'Flashcards',description:'Turn key ideas into questions for recall.'}
];

/** Demo adapters only: no PDF contents are parsed or sent to a server. */
@Injectable({providedIn:'root'})
export class StudyDemoService {
  async generate(tool:ToolId,file:Material):Promise<ToolResult>{
    await new Promise(resolve=>setTimeout(resolve,450));
    const generators:Record<ToolId,()=>ToolResult>={
      summary:()=>({text:`Example summary for ${file.name}\n\n1. Identify the central definition or result.\n2. Explain the reasoning in your own words.\n3. Work through an example and note any open questions.\n\nThis is a demonstration of the summary layout, not a summary extracted from your PDF.`}),
      flashcards:()=>({cards:[{question:'What is the central idea in this material?',answer:'Replace this example with a concise definition from your notes.'},{question:'How would you apply the idea?',answer:'Work through an example, stating each assumption.'}]})
    };
    return generators[tool]();
  }
  async suggest(subjectName:string,fileName?:string):Promise<string>{
    await new Promise(resolve=>setTimeout(resolve,350));
    return fileName?`Spend 25 minutes reviewing ${fileName}, then test yourself on three key ideas.`:`Review one difficult topic in ${subjectName} for 25 minutes, then solve a practice exercise.`;
  }
}
