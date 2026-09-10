import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { StoreService } from '../../shared-services/store.service';
import { AgentCardComponent } from '../agent-card/agent-card.component';
import { SkillsViewComponent } from '../skills-view/skills-view.component';
@Component({ selector:'app-agents-view', standalone:true, imports:[CommonModule,AgentCardComponent,SkillsViewComponent], templateUrl:'./agents-view.component.html', styleUrl:'./agents-view.component.css' })
export class AgentsViewComponent { readonly store=inject(StoreService); readonly router=inject(Router); readonly viewTab=signal('agents'); readonly tab=signal('skills'); readonly agent=computed(()=>this.store.agents().find((item)=>item.id===this.store.selectedAgentId()) ?? null); select(id:string):void{this.store.selectAgent(id)} }
