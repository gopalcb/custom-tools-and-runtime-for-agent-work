import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { StoreService } from '../../shared-services/store.service';
@Component({ selector:'app-workflows-view', standalone:true, imports:[CommonModule], templateUrl:'./workflows-view.component.html', styleUrl:'./workflows-view.component.css' })
export class WorkflowsViewComponent { readonly store=inject(StoreService); readonly activeTab=signal('available'); readonly selectedWorkflowId=signal(''); readonly selected=computed(()=>this.store.workflows().find((workflow)=>workflow.id===(this.selectedWorkflowId()||this.store.workflows()[0]?.id)) ?? null); select(id:string):void{this.selectedWorkflowId.set(id)} }
